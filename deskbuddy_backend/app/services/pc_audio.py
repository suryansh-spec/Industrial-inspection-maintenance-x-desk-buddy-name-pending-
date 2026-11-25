"""
Real-time PC audio analyzer (Windows WASAPI loopback FFT / Core Audio meter).

Streams live Bass / Mid / High / Overall energy and Beat flags to the ESP32
LED ring without relying on the ESP32's onboard microphone.
"""
import asyncio
import logging
import threading
import time
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


class PCAudioService:
    """Captures system output audio via WASAPI loopback and computes 3-band FFT."""

    def __init__(self) -> None:
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._state: Dict[str, int] = {
            "lvl": 0,
            "b": 0,
            "m": 0,
            "h": 0,
            "beat": 0,
        }
        self._last_update = 0.0

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="pc-audio", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None

    def get_frame(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._state)

    def _set_frame(self, lvl: int, b: int, m: int, h: int, beat: int) -> None:
        with self._lock:
            self._state = {"lvl": lvl, "b": b, "m": m, "h": h, "beat": beat}
            self._last_update = time.monotonic()

    def _run_loop(self) -> None:
        """Try WASAPI loopback first; fall back to pycaw IAudioMeterInformation."""
        while self._running:
            try:
                if self._run_wasapi_loopback():
                    continue
            except Exception as exc:
                logger.debug("WASAPI loopback stopped: %s", exc)

            try:
                self._run_pycaw_meter()
            except Exception as exc:
                logger.debug("pycaw meter unavailable: %s", exc)
                self._set_frame(0, 0, 0, 0, 0)
                time.sleep(1.0)

    def _run_wasapi_loopback(self) -> bool:
        try:
            import pyaudiowpatch as pyaudio  # type: ignore
        except ImportError:
            return False

        p = pyaudio.PyAudio()
        stream = None
        try:
            dev = p.get_default_wasapi_loopback()
            rate = int(dev["defaultSampleRate"])
            channels = max(1, int(dev["maxInputChannels"]))
            chunk = 1024

            stream = p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                frames_per_buffer=chunk,
                input=True,
                input_device_index=dev["index"],
            )
            logger.info("PC audio loopback started: %s (%d Hz, %d ch)", dev["name"], rate, channels)

            freqs = np.fft.rfftfreq(chunk, d=1.0 / rate)
            bass_mask = (freqs >= 20) & (freqs < 250)
            mid_mask = (freqs >= 250) & (freqs < 2500)
            high_mask = freqs >= 2500
            window = np.hanning(chunk).astype(np.float32)

            bass_avg = 0.0
            agc_peak = 0.05
            smooth_lvl = 0.0
            smooth_b = 0.0
            smooth_m = 0.0
            smooth_h = 0.0

            while self._running:
                try:
                    raw = stream.read(chunk, exception_on_overflow=False)
                except Exception:
                    break

                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                if channels > 1:
                    samples = samples.reshape(-1, channels).mean(axis=1)

                rms = float(np.sqrt(np.mean(samples * samples)))
                if rms < 0.0008:
                    # True silence / paused
                    smooth_lvl *= 0.6
                    smooth_b *= 0.6
                    smooth_m *= 0.6
                    smooth_h *= 0.6
                    if smooth_lvl < 1.0:
                        self._set_frame(0, 0, 0, 0, 0)
                    else:
                        self._set_frame(int(smooth_lvl), int(smooth_b), int(smooth_m), int(smooth_h), 0)
                    continue

                # Auto-gain control so both quiet and loud tracks stay expressive
                agc_peak = max(rms, agc_peak * 0.992, 0.02)
                norm_lvl = min(100.0, (rms / agc_peak) * 100.0)

                spec = np.abs(np.fft.rfft(samples * window))
                b_raw = float(spec[bass_mask].mean()) if bass_mask.any() else 0.0
                m_raw = float(spec[mid_mask].mean()) if mid_mask.any() else 0.0
                h_raw = float(spec[high_mask].mean()) if high_mask.any() else 0.0

                scale = max(1e-4, agc_peak * (chunk * 0.06))
                b_val = min(100.0, (b_raw / scale) * 100.0)
                m_val = min(100.0, (m_raw / (scale * 0.45)) * 100.0)
                h_val = min(100.0, (h_raw / (scale * 0.2)) * 100.0)

                smooth_lvl = smooth_lvl * 0.35 + norm_lvl * 0.65
                smooth_b = smooth_b * 0.30 + b_val * 0.70
                smooth_m = smooth_m * 0.35 + m_val * 0.65
                smooth_h = smooth_h * 0.35 + h_val * 0.65

                bass_avg = bass_avg * 0.88 + b_val * 0.12
                beat = 1 if (b_val > bass_avg * 1.38 and b_val > 18.0) else 0

                self._set_frame(
                    int(round(smooth_lvl)),
                    int(round(smooth_b)),
                    int(round(smooth_m)),
                    int(round(smooth_h)),
                    beat,
                )
            return True
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            p.terminate()

    def _run_pycaw_meter(self) -> None:
        from ctypes import POINTER, cast
        import comtypes  # type: ignore
        from comtypes import CLSCTX_ALL  # type: ignore
        from pycaw.pycaw import AudioUtilities, IAudioMeterInformation  # type: ignore

        comtypes.CoInitialize()
        try:
            devices = AudioUtilities.GetSpeakers()
            dev = getattr(devices, "_dev", devices)
            interface = dev.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None)
            meter = cast(interface, POINTER(IAudioMeterInformation))
            logger.info("PC audio meter started (pycaw fallback)")

            avg = 0.0
            while self._running:
                peak = float(meter.GetPeakValue() or 0.0)
                lvl = int(min(100.0, peak * 125.0)) if peak > 0.002 else 0
                beat = 1 if (lvl > avg * 1.35 and lvl > 15) else 0
                avg = avg * 0.85 + lvl * 0.15
                self._set_frame(lvl, lvl, lvl, lvl, beat)
                time.sleep(0.04)
        finally:
            comtypes.CoUninitialize()


pc_audio_service = PCAudioService()
