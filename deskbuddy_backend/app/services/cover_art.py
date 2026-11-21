"""Cover Art processing service for DeskBuddy TFT display and web UI.

Converts album artwork into:
1. 40x40 16-bit RGB565 thumbnail for PAGE_MUSIC.
2. 32x40 Gaussian-blurred, darkened RGB565 background for PAGE_LYRICS (upscaled 4x to 128x160 on ESP32 PSRAM).
3. Public high-res URL for web dashboard backdrop.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Dict, Optional, Tuple
import httpx
from PIL import Image, ImageFilter, ImageEnhance

logger = logging.getLogger(__name__)

# In-memory cache for processed RGB565 data and resolved URLs
# Key: f"{title.lower()}|{artist.lower()}"
_ART_CACHE: Dict[str, Dict[str, str]] = {}
_URL_CACHE: Dict[str, str] = {}


def rgb888_to_rgb565_be(r: int, g: int, b: int) -> bytes:
    """Convert RGB888 to 16-bit RGB565 big-endian bytes."""
    r5 = (r >> 3) & 0x1F
    g6 = (g >> 2) & 0x3F
    b5 = (b >> 3) & 0x1F
    val = (r5 << 11) | (g6 << 5) | b5
    return val.to_bytes(2, byteorder="little")


def image_to_rgb565(img: Image.Image) -> bytes:
    """Convert a PIL Image in RGB mode to raw RGB565 bytes (big-endian)."""
    img_rgb = img.convert("RGB")
    data = bytearray()
    for pixel in img_rgb.getdata():
        r, g, b = pixel[:3]
        data.extend(rgb888_to_rgb565_be(r, g, b))
    return bytes(data)


class CoverArtService:
    """Fetches and prepares cover art assets for hardware and web displays."""

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(6.0),
                headers={"User-Agent": "DeskBuddy/2.0 (CoverArtService)"},
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    @staticmethod
    def cache_key(title: str, artist: str) -> str:
        return f"{title.strip().lower()}|{artist.strip().lower()}"

    async def resolve_cover_url(self, title: str, artist: str) -> Optional[str]:
        """Search iTunes for album cover URL if not supplied by media provider."""
        key = self.cache_key(title, artist)
        if key in _URL_CACHE:
            return _URL_CACHE[key]

        if not title:
            return None

        term = f"{title} {artist}".strip()
        client = await self._http()
        try:
            resp = await client.get(
                "https://itunes.apple.com/search",
                params={"term": term, "entity": "song", "limit": 1},
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results and "artworkUrl100" in results[0]:
                    url = results[0]["artworkUrl100"]
                    # Upgrade to higher resolution 600x600 for crisp web display
                    high_res = url.replace("100x100bb.jpg", "600x600bb.jpg")
                    _URL_CACHE[key] = high_res
                    return high_res
        except Exception as exc:
            logger.debug("Failed to resolve cover URL via iTunes: %s", exc)

        return None

    async def get_cover_assets(
        self,
        title: str,
        artist: str,
        album_art_url: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        """Return dict with thumb_b64 (40x40) and bg_b64 (32x40 blurred) in base64."""
        key = self.cache_key(title, artist)
        if key in _ART_CACHE:
            return _ART_CACHE[key]

        target_url = album_art_url or await self.resolve_cover_url(title, artist)
        if not target_url:
            return None

        client = await self._http()
        try:
            resp = await client.get(target_url)
            if resp.status_code != 200:
                return None
            image_bytes = resp.content
        except Exception as exc:
            logger.warning("Failed to download album art from %s: %s", target_url, exc)
            return None

        try:
            with Image.open(io.BytesIO(image_bytes)) as original:
                # 1. 80x80 thumbnail for PAGE_MUSIC (higher resolution)
                thumb_img = original.resize((80, 80), Image.Resampling.LANCZOS)
                thumb_rgb565 = image_to_rgb565(thumb_img)
                thumb_b64 = base64.b64encode(thumb_rgb565).decode("ascii")

                # Dominant color for dynamic theme (quantized)
                try:
                    q = thumb_img.quantize(colors=1, method=Image.Quantize.MEDIANCUT)
                    r, g, b = q.getpalette()[:3]
                    dominant = "#{:02X}{:02X}{:02X}".format(r, g, b)
                except Exception:
                    dominant = None

                # 2. 64x80 blurred, darkened background for PAGE_LYRICS
                # Dim brightness to 22% so overlying lyrics text is sharp and high-contrast
                bg_img = original.resize((64, 80), Image.Resampling.BOX)
                bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=2.5))
                enhancer = ImageEnhance.Brightness(bg_img)
                bg_img = enhancer.enhance(0.22)
                bg_rgb565 = image_to_rgb565(bg_img)
                bg_b64 = base64.b64encode(bg_rgb565).decode("ascii")

                result = {
                    "url": target_url,
                    "thumb_b64": thumb_b64,
                    "bg_b64": bg_b64,
                    "dominant_color": dominant,
                }
                _ART_CACHE[key] = result
                return result
        except Exception as exc:
            logger.exception("Failed to process cover art: %s", exc)
            return None


cover_art_service = CoverArtService()
