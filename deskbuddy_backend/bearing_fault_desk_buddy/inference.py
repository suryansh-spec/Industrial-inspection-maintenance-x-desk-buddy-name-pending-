"""
Backend inference helper.
Input: one raw 1-D vibration signal (or a single 1200-sample window).
Output: predicted bearing condition and class probabilities.
"""
from pathlib import Path
import numpy as np
import torch
from model import CNNModel

class BearingFaultPredictor:
    def __init__(self, checkpoint_path="artifacts/best_model.pth", device=None):
        self.device = torch.device(
            device or ("cuda" if torch.cuda.is_available() else "cpu")
        )
        # Checkpoints produced by this project contain only tensors and basic Python data.
        checkpoint = torch.load(checkpoint_path, map_location=self.device, weights_only=True)
        self.class_names = checkpoint["class_names"]
        self.window_size = int(checkpoint["window_size"])
        self.model = CNNModel(num_classes=len(self.class_names)).to(self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()

    def predict_window(self, window):
        window = np.asarray(window, dtype=np.float32).squeeze()
        if window.ndim != 1 or len(window) != self.window_size:
            raise ValueError(f"Expected a 1-D window of exactly {self.window_size} samples.")
        x = torch.from_numpy(window.copy()).view(1, 1, -1).to(self.device)
        with torch.inference_mode():
            probabilities = torch.softmax(self.model(x), dim=1)[0].cpu().numpy()
        index = int(np.argmax(probabilities))
        return {
            "condition": self.class_names[index],
            "confidence": float(probabilities[index]),
            "probabilities": {
                name: float(prob) for name, prob in zip(self.class_names, probabilities)
            }
        }

    def predict_signal(self, signal, stride=None):
        """Split a longer raw signal into windows and return each prediction + majority vote."""
        signal = np.asarray(signal, dtype=np.float32).squeeze()
        if signal.ndim != 1 or len(signal) < self.window_size:
            raise ValueError(f"Signal must contain at least {self.window_size} samples.")
        stride = stride or self.window_size
        starts = list(range(0, len(signal) - self.window_size + 1, stride))
        results = [
            self.predict_window(signal[start:start + self.window_size])
            for start in starts
        ]
        votes = [item["condition"] for item in results]
        final_condition = max(set(votes), key=votes.count)
        return {
            "condition": final_condition,
            "windows_evaluated": len(results),
            "window_predictions": results
        }

if __name__ == "__main__":
    predictor = BearingFaultPredictor()
    demo = np.random.randn(predictor.window_size).astype(np.float32)
    print(predictor.predict_window(demo))
