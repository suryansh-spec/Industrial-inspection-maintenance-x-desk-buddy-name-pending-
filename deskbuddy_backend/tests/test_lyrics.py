"""Tests for the LRCLIB lyrics parser, cache, and state window."""
import asyncio

from app.services.lyrics import (
    LyricLine,
    LyricsService,
    LyricsTrack,
    lyrics_window,
    parse_lrc,
)


def test_parse_lrc_sorts_and_handles_multiple_tags():
    lrc = "\n".join(
        [
            "[00:12.50]second line",
            "[00:01.00][00:20.00]repeated chorus",
            "[ar:Some Artist]",
            "[00:05.25]third line",
            "",
        ]
    )

    lines = parse_lrc(lrc)

    assert [line.text for line in lines] == [
        "repeated chorus",
        "third line",
        "second line",
        "repeated chorus",
    ]
    assert [line.time_ms for line in lines] == [1000, 5250, 12500, 20000]


def test_parse_lrc_line_times():
    lines = parse_lrc("[00:01.00]one\n[01:02.25]two")

    assert [line.time_ms for line in lines] == [1000, 62250]
    assert [line.text for line in lines] == ["one", "two"]


def test_synced_window_tracks_progress():
    track = LyricsTrack(
        synced=True,
        lines=[
            LyricLine(0, "intro"),
            LyricLine(5000, "first"),
            LyricLine(10000, "second"),
            LyricLine(15000, "third"),
        ],
    )

    window = lyrics_window(track, 12000)

    assert window["available"] is True
    assert window["synced"] is True
    assert window["current"] == "second"
    assert window["prev"] == "first"
    assert window["next"] == "third"
    assert window["index"] == 2


def test_synced_window_before_first_line():
    track = LyricsTrack(
        synced=True,
        lines=[LyricLine(5000, "first"), LyricLine(9000, "second")],
    )

    window = lyrics_window(track, 1000)

    assert window["current"] == ""
    assert window["next"] == "first"
    assert window["index"] == -1


def test_unsynced_window_does_not_pretend_to_scroll():
    track = LyricsTrack(
        synced=False,
        lines=[LyricLine(0, "one"), LyricLine(0, "two"), LyricLine(0, "three")],
    )

    window = lyrics_window(track, 60000)

    assert window["available"] is True
    assert window["synced"] is False
    assert window["current"] == "one"
    assert window["next"] == "two"
    assert window["index"] == 0


def test_repeated_track_lookups_use_the_cache():
    service = LyricsService()
    calls = {"count": 0}

    async def fake_fetch(title, artist, duration_ms):
        calls["count"] += 1
        return LyricsTrack(
            title=title,
            artist=artist,
            synced=True,
            lines=[LyricLine(0, "hello")],
        )

    service._fetch = fake_fetch  # type: ignore[assignment]

    async def load_twice():
        await service.load("Song", "Artist", 1000)
        await service.load("Song", "Artist", 1000)

    asyncio.run(load_twice())

    assert calls["count"] == 1


def test_empty_and_instrumental_tracks():
    empty = lyrics_window(None, 0)
    assert empty["available"] is False
    assert empty["current"] == ""

    instrumental = lyrics_window(
        LyricsTrack(instrumental=True),
        0,
    )
    assert instrumental["available"] is True
    assert instrumental["instrumental"] is True
    assert instrumental["current"] == "Instrumental"
