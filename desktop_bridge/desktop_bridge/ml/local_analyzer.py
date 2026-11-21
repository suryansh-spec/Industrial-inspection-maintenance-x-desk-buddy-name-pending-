"""
Local CNN Analyzer - Edge inference for vibration analysis.
"""
import torch
import numpy as np
import logging
from typing import Dict, Any, Optional
import os

logger = logging.getLogger(__name__)


class LocalVibrationAnalyzer:
    """Local CNN analyzer for edge inference."""
    
    def __init__(self, model_path: Optional[str] = None):
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.class_names = ['Normal', 'Inner Race', 'Ball', 'Outer Race']
        self.window_size = 1200
        self.sampling_rate = 1000
        self._model_loaded = False
        
        if model_path:
            self.load_model(model_path)
    
    def load_model(self, model_path: str) -> bool:
        """Load CNN model from checkpoint."""
        try:
            if not os.path.exists(model_path):
                logger.warning(f"Model not found at {model_path}")
                return False
            
            # Import model architecture
            from desktop_bridge.ml.model import CNNModel
            
            checkpoint = torch.load(model_path, map_location=self.device)
            self.model = CNNModel().to(self.device)
            self.model.load_state_dict(checkpoint['model_state_dict'])
            self.model.eval()
            
            self._model_loaded = True
            logger.info(f"Model loaded from {model_path} on {self.device}")
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False
    
    def is_ready(self) -> bool:
        """Check if model is loaded and ready."""
        return self._model_loaded and self.model is not None
    
    def _prepare_signal(self, signal: np.ndarray) -> Optional[torch.Tensor]:
        """Prepare signal for CNN input."""
        signal = np.asarray(signal, dtype=np.float32).squeeze()
        
        if len(signal) < self.window_size:
            # Pad with zeros
            padded = np.zeros(self.window_size, dtype=np.float32)
            padded[:len(signal)] = signal
            signal = padded
        elif len(signal) > self.window_size:
            # Take center window
            start = (len(signal) - self.window_size) // 2
            signal = signal[start:start + self.window_size]
        
        # Normalize
        signal = signal - signal.mean()
        std = signal.std()
        if std > 1e-12:
            signal = signal / std
        
        # Reshape for CNN: (1, 1, window_size)
        return torch.from_numpy(signal.reshape(1, 1, self.window_size)).float().to(self.device)
    
    async def analyze(
        self, 
        x: np.ndarray, 
        y: np.ndarray, 
        z: np.ndarray, 
        fs: int = 1000
    ) -> Dict[str, Any]:
        """Analyze 3-axis vibration using CNN."""
        
        if not self.is_ready():
            return {
                "status": "model_unavailable",
                "confidence": None,
                "predicted_class": None,
                "error": "CNN model not loaded"
            }
        
        try:
            results = {}
            axis_names = ['x', 'y', 'z']
            signals = [x, y, z]
            
            # Analyze each axis
            for axis_name, signal in zip(axis_names, signals):
                prepared = self._prepare_signal(signal)
                if prepared is None:
                    continue
                
                with torch.no_grad():
                    logits = self.model(prepared)
                    probs = torch.softmax(logits, dim=1).cpu().numpy()[0]
                    pred_class = int(np.argmax(probs))
                    confidence = float(probs[pred_class])
                
                results[axis_name] = {
                    "predicted_class": self.class_names[pred_class],
                    "class_index": pred_class,
                    "confidence": confidence,
                    "probabilities": {
                        name: float(prob) 
                        for name, prob in zip(self.class_names, probs)
                    }
                }
            
            # Aggregate: use worst axis (highest fault probability)
            fault_scores = {}
            for axis_name, result in results.items():
                fault_prob = sum(
                    result['probabilities'][name] 
                    for name in self.class_names[1:]  # Sum fault probabilities
                )
                fault_scores[axis_name] = fault_prob
            
            worst_axis = max(fault_scores, key=fault_scores.get) if fault_scores else 'x'
            worst_result = results[worst_axis]
            is_fault = worst_result['class_index'] != 0
            
            return {
                "status": "anomaly_detected" if is_fault else "normal",
                "confidence": worst_result['confidence'],
                "predicted_class": worst_result['predicted_class'],
                "worst_axis": worst_axis,
                "axis_results": results,
                "model_type": "cnn",
                "window_size": self.window_size,
                "sampling_rate": self.sampling_rate
            }
            
        except Exception as e:
            logger.error(f"CNN analysis error: {e}")
            return {
                "status": "error",
                "confidence": None,
                "predicted_class": None,
                "error": str(e)
            }
    
    def analyze_sync(
        self, 
        x: np.ndarray, 
        y: np.ndarray, 
        z: np.ndarray, 
        fs: int = 1000
    ) -> Dict[str, Any]:
        """Synchronous version for non-async contexts."""
        import asyncio
        return asyncio.run(self.analyze(x, y, z, fs))


# Convenience function for quick analysis
async def analyze_vibration_local(
    x: np.ndarray, 
    y: np.ndarray, 
    z: np.ndarray, 
    fs: int = 1000,
    model_path: Optional[str] = None
) -> Dict[str, Any]:
    """Quick analysis function."""
    analyzer = LocalVibrationAnalyzer(model_path)
    return await analyzer.analyze(x, y, z, fs)