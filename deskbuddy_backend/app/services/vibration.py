"""
Vibration analysis service.

Tries the trained CNN when available and otherwise falls back to a
numpy-only statistical analysis so the API always returns a useful result.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import PROJECT_ROOT, settings

logger = logging.getLogger(__name__)

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy is a runtime dependency
    np = None


CLASS_NAMES = ["Normal", "Inner Race", "Ball", "Outer Race"]


class LocalAnalyzer:
    """Optional CNN-based analyzer with graceful degradation."""

    def __init__(self):
        self.model = None
        self.device = "cpu"
        self.window_size = 1200
        self.sampling_rate = 1000
        self.class_names = CLASS_NAMES
        self._load_attempted = False
        self._model_loaded = False

    def is_ready(self) -> bool:
        self._ensure_model()
        return self._model_loaded and self.model is not None

    def _ensure_model(self) -> None:
        if self._load_attempted:
            return
        self._load_attempted = True

        model_path = Path(settings.ml_model_path)
        if not model_path.is_absolute():
            model_path = PROJECT_ROOT / model_path

        if not model_path.exists():
            logger.info("CNN model not found at %s - using traditional analysis", model_path)
            return

        try:
            import torch
        except Exception:
            logger.info("PyTorch not available - using traditional vibration analysis")
            return

        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        try:
            from bearing_fault_desk_buddy.model import CNNModel

            checkpoint = torch.load(model_path, map_location=self.device, weights_only=True)
            model = CNNModel()
            state_dict = checkpoint.get("model_state_dict", checkpoint)
            model.load_state_dict(state_dict)
            model.eval()
            model.to(self.device)

            self.model = model
            self._model_loaded = True
            logger.info("Vibration CNN loaded from %s on %s", model_path, self.device)
        except Exception as exc:
            logger.warning("Could not load vibration CNN (%s) - using traditional analysis", exc)

    def _prepare(self, signal):
        import torch

        signal = np.asarray(signal, dtype=np.float32).squeeze()
        if signal.size < self.window_size:
            padded = np.zeros(self.window_size, dtype=np.float32)
            padded[: signal.size] = signal
            signal = padded
        elif signal.size > self.window_size:
            start = (signal.size - self.window_size) // 2
            signal = signal[start : start + self.window_size]

        signal = signal - signal.mean()
        std = signal.std()
        if std > 1e-12:
            signal = signal / std

        tensor = torch.from_numpy(signal.reshape(1, 1, self.window_size)).float()
        return tensor.to(self.device)

    async def analyze_cnn(self, axes: Dict[str, Any]) -> Dict[str, Any]:
        import torch

        results: Dict[str, Any] = {}
        for axis_name, signal in axes.items():
            tensor = self._prepare(signal)
            with torch.no_grad():
                logits = self.model(tensor)
                probs = torch.softmax(logits, dim=1).cpu().numpy()[0]
                predicted = int(np.argmax(probs))

            results[axis_name] = {
                "predicted_class": self.class_names[predicted],
                "class_index": predicted,
                "confidence": float(probs[predicted]),
                "probabilities": {
                    name: float(prob) for name, prob in zip(self.class_names, probs)
                },
            }

        fault_scores = {
            axis: sum(result["probabilities"][name] for name in self.class_names[1:])
            for axis, result in results.items()
        }
        worst_axis = max(fault_scores, key=fault_scores.get) if fault_scores else "x"
        worst = results[worst_axis]
        is_fault = worst["class_index"] != 0

        return {
            "status": "anomaly_detected" if is_fault else "normal",
            "predicted_class": worst["predicted_class"],
            "confidence": worst["confidence"],
            "worst_axis": worst_axis,
            "axis_results": results,
            "model_type": "cnn",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class TraditionalAnalyzer:
    """Statistical fallback: RMS, kurtosis and crest factor per axis."""

    @staticmethod
    def _features(signal) -> Dict[str, float]:
        arr = np.asarray(signal, dtype=np.float64).flatten()
        if arr.size == 0:
            return {"rms": 0.0, "kurtosis": 0.0, "crest": 0.0, "peak": 0.0}

        centered = arr - arr.mean()
        rms = float(np.sqrt(np.mean(centered**2)))
        peak = float(np.max(np.abs(centered)))
        m2 = float(np.mean(centered**2))
        m4 = float(np.mean(centered**4))
        kurtosis = m4 / (m2 * m2 + 1e-12)
        crest = peak / (rms + 1e-12)

        return {
            "rms": rms,
            "kurtosis": kurtosis,
            "crest": crest,
            "peak": peak,
        }

    def analyze(self, axes: Dict[str, Any]) -> Dict[str, Any]:
        features = {axis: self._features(values) for axis, values in axes.items()}
        scores = {axis: f["kurtosis"] for axis, f in features.items()}
        worst_axis = max(scores, key=scores.get) if scores else "x"
        worst = features.get(worst_axis, {"kurtosis": 0.0, "crest": 0.0})

        kurtosis = worst["kurtosis"]
        if kurtosis >= 8.0:
            predicted_class = "Outer Race"
            status = "anomaly_detected"
        elif kurtosis >= 5.0:
            predicted_class = "Inner Race"
            status = "anomaly_detected"
        elif kurtosis >= 3.5:
            predicted_class = "Ball"
            status = "anomaly_detected"
        else:
            predicted_class = "Normal"
            status = "normal"

        confidence = min(0.99, 0.5 + abs(kurtosis - 3.0) * 0.08)
        axis_results = {
            axis: {
                "predicted_class": "Normal" if f["kurtosis"] < 3.5 else predicted_class,
                "confidence": round(min(0.99, 0.5 + abs(f["kurtosis"] - 3.0) * 0.08), 4),
                "features": {key: round(value, 6) for key, value in f.items()},
            }
            for axis, f in features.items()
        }

        return {
            "status": status,
            "predicted_class": predicted_class,
            "confidence": round(confidence, 4),
            "worst_axis": worst_axis,
            "axis_results": axis_results,
            "metrics": {
                "kurtosis": round(kurtosis, 4),
                "crest_factor": round(worst["crest"], 4),
            },
            "model_type": "traditional",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


local_analyzer = LocalAnalyzer()
traditional_analyzer = TraditionalAnalyzer()


async def analyze(
    x,
    y,
    z,
    sample_rate_hz: int = 1000,
    method: str = "auto",
) -> Dict[str, Any]:
    """Analyze 3-axis vibration data.

    ``method`` is one of ``auto``, ``cnn``, ``traditional`` or ``both``.
    """
    if np is None:
        return {
            "status": "error",
            "predicted_class": None,
            "confidence": None,
            "error": "numpy is not installed",
        }

    axes = {"x": x, "y": y, "z": z}
    cnn_ready = local_analyzer.is_ready()

    if method == "cnn" and not cnn_ready:
        return {
            "status": "model_unavailable",
            "predicted_class": None,
            "confidence": None,
            "worst_axis": None,
            "model_type": "cnn",
            "error": "CNN model is not available",
        }

    if method == "traditional" or (method == "auto" and not cnn_ready):
        return traditional_analyzer.analyze(axes)

    if method == "cnn":
        return await local_analyzer.analyze_cnn(axes)

    if method == "both":
        traditional = traditional_analyzer.analyze(axes)
        if cnn_ready:
            traditional["cnn"] = await local_analyzer.analyze_cnn(axes)
        return traditional

    # auto with CNN available
    try:
        return await local_analyzer.analyze_cnn(axes)
    except Exception as exc:  # pragma: no cover - inference dependent
        logger.error("CNN analysis failed (%s) - falling back to traditional", exc)
        return traditional_analyzer.analyze(axes)
