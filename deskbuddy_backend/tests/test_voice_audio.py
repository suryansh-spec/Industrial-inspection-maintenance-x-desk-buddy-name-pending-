"""Tests for the voice pipeline audio helpers."""
import numpy as np
import pytest

from app.services import voice_audio


def test_pcm16_wav_round_trip():
    samples = (np.sin(np.linspace(0, 2 * np.pi * 440, 16000)) * 12000).astype(np.int16)
    wav = voice_audio.pcm16_to_wav(samples, 16000)

    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"

    decoded, sample_rate = voice_audio.decode_audio_to_pcm16(wav, 16000)
    assert sample_rate == 16000
    assert len(decoded) == len(samples)
    assert np.max(np.abs(decoded.astype(np.int32) - samples.astype(np.int32))) <= 2


def test_resamples_8k_to_16k():
    samples = np.zeros(8000, dtype=np.int16)
    samples[::100] = 10000
    wav = voice_audio.pcm16_to_wav(samples, 8000)

    decoded, sample_rate = voice_audio.decode_audio_to_pcm16(wav, 16000)
    assert sample_rate == 16000
    assert abs(len(decoded) - 16000) <= 2
    assert decoded.dtype == np.int16


def test_empty_audio_is_rejected():
    with pytest.raises(ValueError):
        voice_audio.decode_audio_to_pcm16(b"")


def test_stereo_is_downmixed():
    left = np.full(4000, 8000, dtype=np.int16)
    right = np.full(4000, -8000, dtype=np.int16)
    interleaved = np.empty(8000, dtype=np.int16)
    interleaved[0::2] = left
    interleaved[1::2] = right

    wav = voice_audio.pcm16_to_wav(interleaved, 16000, channels=2)
    decoded, sample_rate = voice_audio.decode_audio_to_pcm16(wav, 16000)

    assert sample_rate == 16000
    assert len(decoded) == 4000
    # Left/right cancel out when averaged.
    assert abs(int(decoded.mean())) <= 2
