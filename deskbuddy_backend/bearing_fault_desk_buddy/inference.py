"""
Backend inference helper.
Input: one raw 1-D vibration signal (or a single window).
Output: predicted bearing condition and class probabilities.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
import torch

from model import ExtensiveCNN


class BearingFaultPredictor:
    """Load a trained ExtensiveCNN checkpoint and predict bearing condition."""

    def __init__(
        self,
        checkpoint_path: str = "artifacts/best_model.pth",
        device: Optional[str] = None,
    ):
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        checkpoint = torch.load(checkpoint_path, map_location=self.device, weights_only=True)

        self.class_names: List[str] = checkpoint["class_names"]
        self.window_size: int = int(checkpoint["window_size"])
        self.in_channels: int = int(checkpoint.get("input_channels", 1))
        # Derive variant from architecture string (e.g. "ExtensiveCNN-light" -> "light")
        arch = checkpoint.get("architecture", "ExtensiveCNN-light")
        self.variant: str = arch.split("-")[-1] if "-" in arch else "light"
        self.use_spectral: bool = bool(checkpoint.get("use_spectral", False))

        self.model = ExtensiveCNN(
            num_classes=len(self.class_names),
            in_channels=self.in_channels,
            variant=self.variant,
            window_size=self.window_size,
            use_spectral=self.use_spectral,
        ).to(self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()

    @torch.inference_mode()
    def _predict_tensor(self, x: torch.Tensor) -> Dict:
        """x: (1, channels, window_size) on self.device."""
        logits = self.model(x)
        probabilities = torch.softmax(logits, dim=1)[0].cpu().numpy()
        index = int(np.argmax(probabilities))
        return {
            "condition": self.class_names[index],
            "confidence": float(probabilities[index]),
            "probabilities": {
                name: float(prob) for name, prob in zip(self.class_names, probabilities)
            },
        }

    def predict_window(self, window) -> Dict:
        """Predict on a single 1-D vibration window."""
        window = np.asarray(window, dtype=np.float32).squeeze()
        if window.ndim != 1:
            raise ValueError("Expected a 1-D vibration window.")
        if self.in_channels == 1:
            x = torch.from_numpy(window.copy()).view(1, 1, -1).to(self.device)
        else:
            # Replicate single axis into in_channels identical channels
            x = torch.from_numpy(np.stack([window] * self.in_channels)).view(1, self.in_channels, -1).to(self.device)
        if x.shape[-1] != self.window_size:
            raise ValueError(f"Expected a window of exactly {self.window_size} samples, got {x.shape[-1]}.")
        return self._predict_tensor(x)

    def predict_signal(self, signal, stride: Optional[int] = None) -> Dict:
        """Split a longer raw signal into windows and return each prediction + majority vote."""
        signal = np.asarray(signal, dtype=np.float32).squeeze()
        if signal.ndim != 1 or len(signal) < self.window_size:
            raise ValueError(f"Signal must contain at least {self.window_size} samples.")
        stride = stride or self.window_size
        starts = list(range(0, len(signal) - self.window_size + 1, stride))
        results = [self.predict_window(signal[start:start + self.window_size]) for start in starts]
        votes = [item["condition"] for item in results]
        final_condition = max(set(votes), key=votes.count)
        return {
            "condition": final_condition,
            "windows_evaluated": len(results),
            "window_predictions": results,
        }


if __name__ == "__main__":
    import glob
    ckpts = glob.glob("artifacts/best_model.pth")
    if not ckpts:
        print("No checkpoint found at artifacts/best_model.pth. Train first with: python main.py")
    else:
        predictor = BearingFaultPredictor()
        demo = np.random.randn(predictor.window_size).astype(np.float32)
        print(predictor.predict_window(demo))
