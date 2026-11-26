"""Audio helpers for the DeskBuddy voice assistant.

The ESP32 records 16 kHz mono PCM WAV and uploads it over Wi-Fi.  The backend
uses faster-whisper for speech-to-text and edge-tts for neural text-to-speech.
edge-tts returns MP3, so this module decodes it to the PCM WAV format the
MAX98357A / I2S output expects.

All decoding falls back to the standard-library ``wave`` reader for plain PCM
WAV files, and TTS falls back to Windows SAPI when edge-tts is unavailable.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile
import wave
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1


def _resample(mono: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Resample mono float32 audio with a polyphase filter."""
    if src_sr == dst_sr or mono.size == 0:
        return mono
    from math import gcd

    from scipy.signal import resample_poly

    factor = gcd(int(src_sr), int(dst_sr))
    up = int(dst_sr) // factor
    down = int(src_sr) // factor
    return resample_poly(mono, up, down).astype(np.float32)


def decode_audio_to_pcm16(
    data: bytes,
    target_sr: int = TARGET_SAMPLE_RATE,
) -> Tuple[np.ndarray, int]:
    """Decode WAV/MP3/FLAC/OGG bytes to mono int16 PCM at ``target_sr``.

    Returns ``(pcm, sample_rate)``.  Raises ``ValueError`` if the payload is
    not decodable audio.
    """
    if not data:
        raise ValueError("empty audio payload")

    mono: Optional[np.ndarray] = None
    src_sr = int(target_sr)

    # Preferred path: libsndfile handles WAV, FLAC, OGG, and (>= 1.2) MP3.
    try:
        import soundfile as sf

        audio, src_sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
        if audio.size:
            mono = audio.mean(axis=1) if audio.shape[1] > 1 else audio[:, 0]
    except Exception as exc:  # pragma: no cover - depends on libsndfile build
        logger.debug("soundfile decode failed (%s); trying wave reader", exc)

    # Fallback: standard-library PCM WAV reader.
    if mono is None:
        try:
            with wave.open(io.BytesIO(data), "rb") as wf:
                src_sr = wf.getframerate()
                channels = wf.getnchannels()
                width = wf.getsampwidth()
                raw = wf.readframes(wf.getnframes())
            if width == 2:
                arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            elif width == 4:
                arr = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
            elif width == 1:
                arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
            else:
                raise ValueError(f"unsupported WAV sample width: {width}")
            if channels > 1:
                arr = arr.reshape(-1, channels).mean(axis=1)
            mono = arr
        except Exception as exc:
            raise ValueError(f"could not decode audio: {exc}") from exc

    if mono is None or mono.size == 0:
        raise ValueError("decoded audio is empty")

    mono = np.nan_to_num(np.asarray(mono, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    mono = _resample(mono, int(src_sr), int(target_sr))
    mono = np.clip(mono, -1.0, 1.0)
    pcm = (mono * 32767.0).astype(np.int16)
    return pcm, int(target_sr)


def pcm16_to_wav(
    pcm: np.ndarray,
    sample_rate: int = TARGET_SAMPLE_RATE,
    channels: int = TARGET_CHANNELS,
) -> bytes:
    """Wrap mono/stereo int16 PCM in a standard 44-byte WAV container."""
    raw = np.asarray(pcm, dtype=np.int16).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(int(channels))
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(raw)
    return buf.getvalue()


def _sapi_tts_wav(text: str, sample_rate: int = TARGET_SAMPLE_RATE) -> Optional[bytes]:
    """Render text to WAV with Windows SAPI (offline fallback)."""
    try:
        import win32com.client  # type: ignore
    except Exception:
        return None

    tmp_path: Optional[str] = None
    stream = None
    com_inited = False
    try:
        try:
            import pythoncom  # type: ignore
            pythoncom.CoInitialize()
            com_inited = True
        except Exception:
            pass

        fd, tmp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

        voice = win32com.client.Dispatch("SAPI.SpVoice")
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        # SSFMCreateForWrite = 3
        stream.Open(tmp_path, 3, False)

        # SpeechAudioFormatType: 18 = SAFT16kHz16BitMono, 22 = SAFT22kHz16BitMono.
        try:
            fmt = win32com.client.Dispatch("SAPI.SpAudioFormat")
            fmt.Type = 18 if sample_rate == 16000 else 22
            stream.Format = fmt
        except Exception:
            pass

        voice.AudioOutputStream = stream
        voice.Speak(text)
        stream.Close()
        stream = None

        with open(tmp_path, "rb") as fh:
            return fh.read()
    except Exception as exc:  # pragma: no cover - Windows COM dependent
        logger.debug("SAPI TTS failed: %s", exc)
        return None
    finally:
        if stream is not None:
            try:
                stream.Close()
            except Exception:
                pass
        if com_inited:
            try:
                import pythoncom  # type: ignore
                pythoncom.CoUninitialize()
            except Exception:
                pass
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


async def tts_to_pcm16(
    text: str,
    voice: str = "en-US-ChristopherNeural",
    speed: float = 1.0,
) -> Tuple[np.ndarray, int]:
    """Synthesize speech and return mono int16 PCM at 16 kHz.

    Tries edge-tts first (natural neural voice, requires network) and falls
    back to Windows SAPI for offline operation.
    """
    text = (text or "").strip()
    if not text:
        return np.zeros(0, dtype=np.int16), TARGET_SAMPLE_RATE

    # 1. edge-tts neural voice.
    try:
        import edge_tts

        rate_str = f"{int((speed - 1.0) * 100):+d}%"
        communicate = edge_tts.Communicate(text, voice, rate=rate_str)
        mp3 = bytearray()
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                mp3.extend(chunk["data"])
        if mp3:
            return await asyncio.to_thread(decode_audio_to_pcm16, bytes(mp3), TARGET_SAMPLE_RATE)
    except Exception as exc:
        logger.warning("edge-tts failed (%s); falling back to SAPI", exc)

    # 2. Windows SAPI offline fallback.
    wav = await asyncio.to_thread(_sapi_tts_wav, text, TARGET_SAMPLE_RATE)
    if wav:
        try:
            return await asyncio.to_thread(decode_audio_to_pcm16, wav, TARGET_SAMPLE_RATE)
        except Exception as exc:  # pragma: no cover - Windows COM dependent
            logger.warning("SAPI WAV decode failed: %s", exc)

    raise RuntimeError("TTS unavailable: edge-tts failed and SAPI fallback is unavailable")
