"""Synchronized lyrics for the DeskBuddy lyrics screen.

LRCLIB supplies timed LRC lyrics and a plain-text fallback. The service is
deliberately independent of the music provider: it looks tracks up by title,
artist and duration, so it works with YouTube Music and the Windows Media
Player fallback alike.

Lookups are cached per track and never happen on the 1 Hz state path unless the
track actually changed.
"""
from __future__ import annotations

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

LRCLIB_BASE = "https://lrclib.net/api"
USER_AGENT = "DeskBuddy/2.0 (ESP32 desk companion; local desktop app)"
CACHE_MAX_ENTRIES = 128
CACHE_TTL_SECONDS = 6 * 60 * 60
NEGATIVE_TTL_SECONDS = 15 * 60

_LRC_TAG = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")


@dataclass
class LyricLine:
    time_ms: int
    text: str


@dataclass
class LyricsTrack:
    title: str = ""
    artist: str = ""
    album: str = ""
    duration_ms: int = 0
    synced: bool = False
    instrumental: bool = False
    source: str = "lrclib"
    lines: List[LyricLine] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.instrumental or bool(self.lines)


def parse_lrc(text: str) -> List[LyricLine]:
    """Parse LRC text into time-sorted lines."""

    lines: List[LyricLine] = []
    for raw in (text or "").splitlines():
        tags = list(_LRC_TAG.finditer(raw))
        if not tags:
            continue
        content = _LRC_TAG.sub("", raw).strip()
        if not content:
            continue
        for tag in tags:
            minutes = int(tag.group(1))
            seconds = float(tag.group(2))
            lines.append(
                LyricLine(time_ms=int((minutes * 60 + seconds) * 1000), text=content)
            )
    lines.sort(key=lambda line: line.time_ms)
    return lines


class LyricsService:
    """LRCLIB client with an in-memory per-track cache."""

    def __init__(self) -> None:
        self._cache: "OrderedDict[str, Tuple[Optional[LyricsTrack], float]]" = (
            OrderedDict()
        )
        self._client: Optional[httpx.AsyncClient] = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=LRCLIB_BASE,
                timeout=httpx.Timeout(6.0),
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    @staticmethod
    def cache_key(title: str, artist: str, duration_ms: int = 0) -> str:
        return "|".join(
            [
                (title or "").strip().lower(),
                (artist or "").strip().lower(),
                str(int(round((duration_ms or 0) / 1000))),
            ]
        )

    def _cached(self, key: str) -> Tuple[bool, Optional[LyricsTrack]]:
        entry = self._cache.get(key)
        if not entry:
            return False, None
        track, expires_at = entry
        import time

        if time.time() >= expires_at:
            self._cache.pop(key, None)
            return False, None
        self._cache.move_to_end(key)
        return True, track

    def _store(self, key: str, track: Optional[LyricsTrack]) -> None:
        import time

        ttl = CACHE_TTL_SECONDS if track and track.available else NEGATIVE_TTL_SECONDS
        self._cache[key] = (track, time.time() + ttl)
        self._cache.move_to_end(key)
        while len(self._cache) > CACHE_MAX_ENTRIES:
            self._cache.popitem(last=False)

    async def load(
        self,
        title: str,
        artist: str,
        duration_ms: int = 0,
    ) -> Optional[LyricsTrack]:
        """Resolve lyrics for a track, using the cache when possible."""

        if not title:
            return None

        key = self.cache_key(title, artist, duration_ms)
        hit, cached = self._cached(key)
        if hit:
            return cached

        track = await self._fetch(title, artist, duration_ms)
        self._store(key, track)
        return track

    async def _fetch(
        self,
        title: str,
        artist: str,
        duration_ms: int,
    ) -> Optional[LyricsTrack]:
        params: Dict[str, Any] = {
            "track_name": title,
            "artist_name": artist or "",
        }
        if duration_ms:
            params["duration"] = int(round(duration_ms / 1000))

        try:
            client = await self._http()
            response = await client.get("/get", params=params)
            if response.status_code == 200:
                track = self._from_payload(response.json())
                if track and track.available:
                    return track
            elif response.status_code != 404:
                logger.warning("LRCLIB get failed: HTTP %s", response.status_code)
        except Exception as exc:
            logger.warning("LRCLIB get error: %s", exc)

        # The exact match endpoint is strict; search and pick the closest
        # duration when the duration metadata from the player is approximate.
        try:
            client = await self._http()
            response = await client.get(
                "/search",
                params={"track_name": title, "artist_name": artist or ""},
            )
            if response.status_code == 200:
                results = response.json()
                if isinstance(results, list):
                    best = self._best_match(results, title, artist, duration_ms)
                    if best:
                        track = self._from_payload(best, title, artist, duration_ms)
                        if track and track.available:
                            return track
        except Exception as exc:
            logger.warning("LRCLIB search error: %s", exc)

        return None

    @staticmethod
    def _best_match(
        results: Iterable[Dict[str, Any]],
        title: str,
        artist: str,
        duration_ms: int,
    ) -> Optional[Dict[str, Any]]:
        wanted_title = (title or "").strip().lower()
        wanted_artist = (artist or "").strip().lower()
        wanted_seconds = duration_ms / 1000 if duration_ms else 0

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            item_title = str(item.get("trackName") or "").strip().lower()
            item_artist = str(item.get("artistName") or "").strip().lower()
            if wanted_title and wanted_title not in item_title:
                continue
            if wanted_artist and wanted_artist not in item_artist:
                continue
            if not (item.get("syncedLyrics") or item.get("plainLyrics")):
                continue
            score = 0.0
            if item_title == wanted_title:
                score += 2.0
            if item_artist == wanted_artist:
                score += 2.0
            item_duration = item.get("duration")
            if wanted_seconds and isinstance(item_duration, (int, float)):
                score -= abs(float(item_duration) - wanted_seconds) / 10.0
            scored.append((score, item))

        if not scored:
            return None
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[0][1]

    @staticmethod
    def _from_payload(
        payload: Dict[str, Any],
        title: str = "",
        artist: str = "",
        duration_ms: int = 0,
    ) -> Optional[LyricsTrack]:
        if not isinstance(payload, dict):
            return None

        raw_synced = payload.get("syncedLyrics") or ""
        raw_plain = payload.get("plainLyrics") or ""
        instrumental = bool(payload.get("instrumental"))

        track = LyricsTrack(
            title=str(payload.get("trackName") or title or ""),
            artist=str(payload.get("artistName") or artist or ""),
            album=str(payload.get("albumName") or ""),
            duration_ms=int(
                (payload.get("duration") or 0) * 1000
                if payload.get("duration")
                else duration_ms
            ),
            instrumental=instrumental,
            source="lrclib",
        )

        lines = parse_lrc(raw_synced) if raw_synced else []
        if lines:
            track.synced = True
            track.lines = lines
            return track

        if raw_plain:
            track.lines = [
                LyricLine(time_ms=0, text=line.strip())
                for line in raw_plain.splitlines()
                if line.strip()
            ]
            return track

        return track if instrumental else None


def lyrics_window(
    track: Optional[LyricsTrack],
    progress_ms: int,
) -> Dict[str, Any]:
    """Return the previous/current/next lines for the 1 Hz state packet."""

    if track is None or not track.available:
        return {
            "available": False,
            "synced": False,
            "instrumental": False,
            "source": None,
            "index": -1,
            "total": 0,
            "prev": "",
            "current": "",
            "next": "",
        }

    if track.instrumental:
        return {
            "available": True,
            "synced": False,
            "instrumental": True,
            "source": track.source,
            "index": -1,
            "total": 0,
            "prev": "",
            "current": "Instrumental",
            "next": "",
        }

    lines = track.lines
    if track.synced:
        index = -1
        for position, line in enumerate(lines):
            if line.time_ms <= progress_ms + 500:
                index = position
            else:
                break
    else:
        # No timing information: keep the first lines visible and let the
        # firmware show an "UNSYNCED" badge instead of pretending to scroll.
        index = 0

    def text_at(position: int) -> str:
        if 0 <= position < len(lines):
            return lines[position].text
        return ""

    return {
        "available": True,
        "synced": track.synced,
        "instrumental": False,
        "source": track.source,
        "index": index,
        "total": len(lines),
        "prev": text_at(index - 1),
        "current": text_at(index),
        "next": text_at(index + 1),
    }


lyrics_service = LyricsService()
