"""
Traditional Vibration Analysis - Feature extraction + Isolation Forest.
"""
import numpy as np
from scipy import signal
from scipy.fft import fft, rfft, rfftfreq
from typing import Dict, Any, List, Tuple
import logging
import joblib
import os

logger = logging.getLogger(__name__)

# Global Isolation Forest model
_if_model = None
_model_path = os.path.join(os.path.dirname(__file__), "models", "isolation_forest.pkl")


def load_isolation_forest(path: Optional[str] = None) -> bool:
    """Load Isolation Forest model."""
    global _if_model
    model_path = path or _model_path
    
    try:
        if os.path.exists(model_path):
            _if_model = joblib.load(model_path)
            logger.info(f"Isolation Forest loaded from {model_path}")
            return True
        else:
            logger.warning(f"Isolation Forest model not found at {model_path}")
            return False
    except Exception as e:
        logger.error(f"Failed to load Isolation Forest: {e}")
        return False


def extract_features(x: np.ndarray, fs: float) -> Dict[str, float]:
    """
    Extract vibration features from signal.
    
    Args:
        x: 1D vibration signal
        fs: Sampling frequency in Hz
        
    Returns:
        Dictionary of extracted features
    """
    x = np.asarray(x, float)
    x = x - x.mean()
    
    # Bandpass 1-400 Hz (typical for rotating machinery)
    sos = signal.butter(4, [1, 400], btype="bandpass", fs=fs, output="sos")
    xf = signal.sosfiltfilt(sos, x)

    rms = float(np.sqrt(np.mean(xf**2)))
    peak = float(np.max(np.abs(xf)))
    p2p = float(xf.max() - xf.min())
    crest = float(peak / rms) if rms > 1e-12 else 0.0
    var = float(np.var(xf))
    kurt = float(np.mean((xf - xf.mean())**4) / var**2) if var > 1e-12 else 0.0

    n = len(xf)
    freqs = rfftfreq(n, 1/fs)
    mag = np.abs(rfft(xf)) / n
    mask = freqs > 2
    dom_f = float(freqs[mask][np.argmax(mag[mask])]) if mask.any() else 0.0

    psd = mag**2
    s = psd.sum()
    if s > 0:
        pn = psd / s
        nz = pn[pn > 0]
        spec_entropy = float(-np.sum(nz * np.log2(nz)))
        centroid = float((freqs * psd).sum() / s)
    else:
        spec_entropy, centroid = 0.0, 0.0

    return {
        "rms": rms, 
        "peak": peak, 
        "p2p": p2p, 
        "crest": crest,
        "kurtosis": kurt, 
        "dominant_freq_hz": dom_f,
        "spectral_entropy": spec_entropy, 
        "spectral_centroid_hz": centroid,
    }


def extract_all_axis_features(
    x: np.ndarray, 
    y: np.ndarray, 
    z: np.ndarray, 
    fs: float
) -> Dict[str, Dict[str, float]]:
    """Extract features for all three axes."""
    return {
        "x": extract_features(x, fs),
        "y": extract_features(y, fs),
        "z": extract_features(z, fs)
    }


def get_worst_axis(features: Dict[str, Dict[str, float]]) -> Tuple[str, Dict[str, float]]:
    """Get axis with highest kurtosis (most indicative of faults)."""
    return max(features.items(), key=lambda kv: kv[1].get("kurtosis", 0))


def analyze_traditional_features(
    x: np.ndarray, 
    y: np.ndarray, 
    z: np.ndarray, 
    fs: float = 1000
) -> Dict[str, Any]:
    """
    Analyze vibration using traditional features + Isolation Forest.
    
    Returns:
        Dictionary with analysis results
    """
    # Extract features for all axes
    feats = extract_all_axis_features(x, y, z, fs)
    
    # Find worst axis
    worst_axis, worst_feats = get_worst_axis(feats)
    
    # Try Isolation Forest if available
    if _if_model is not None:
        try:
            vec = [[
                worst_feats.get("rms", 0),
                worst_feats.get("peak", 0),
                worst_feats.get("p2p", 0),
                worst_feats.get("crest", 0),
                worst_feats.get("kurtosis", 0),
                worst_feats.get("dominant_freq_hz", 0),
                worst_feats.get("spectral_entropy", 0),
                worst_feats.get("spectral_centroid_hz", 0)
            ]]
            
            score = float(_if_model.score_samples(vec)[0])  # higher = more normal
            is_anom = score < -0.05  # threshold from validation
            
            return {
                "status": "anomaly_detected" if is_anom else "normal",
                "confidence": float(min(1.0, max(0.0, (0.1 - score) * 4))),
                "metrics": worst_feats,
                "worst_axis": worst_axis,
                "model_type": "isolation_forest"
            }
        except Exception as e:
            logger.warning(f"Isolation Forest failed: {e}")
    
    # Fallback to heuristic
    anomaly = (
        worst_feats.get("kurtosis", 0) > 5.0 or 
        worst_feats.get("crest", 0) > 6.0 or
        worst_feats.get("rms", 0) > 2.0
    )
    
    return {
        "status": "anomaly_detected" if anomaly else "normal",
        "confidence": None,
        "metrics": worst_feats,
        "worst_axis": worst_axis,
        "model_type": "heuristic"
    }


def analyze_traditional(
    x: np.ndarray, 
    y: np.ndarray, 
    z: np.ndarray, 
    fs: float = 1000
) -> Dict[str, Any]:
    """
    Main entry point for traditional analysis (async wrapper).
    """
    import asyncio
    return asyncio.get_event_loop().run_in_executor(
        None, analyze_traditional_features, x, y, z, fs
    )


def get_feature_vector(
    x: np.ndarray, 
    y: np.ndarray, 
    z: np.ndarray, 
    fs: float = 1000
) -> List[float]:
    """
    Get feature vector for ML models.
    Returns 24 features (8 per axis * 3 axes).
    """
    feats = extract_all_axis_features(x, y, z, fs)
    feature_names = [
        "rms", "peak", "p2p", "crest", 
        "kurtosis", "dominant_freq_hz",
        "spectral_entropy", "spectral_centroid_hz"
    ]
    
    vector = []
    for axis in ["x", "y", "z"]:
        for name in feature_names:
            vector.append(feats[axis].get(name, 0.0))
    
    return vector


def train_isolation_forest(
    X_train: np.ndarray,
    contamination: float = 0.05,
    n_estimators: int = 100,
    save_path: Optional[str] = None
):
    """
    Train Isolation Forest on normal data.
    
    Args:
        X_train: Training data (n_samples, n_features) - should be normal data only
        contamination: Expected proportion of outliers
        n_estimators: Number of trees
        save_path: Path to save model
    """
    from sklearn.ensemble import IsolationForest
    
    model = IsolationForest(
        contamination=contamination,
        n_estimators=n_estimators,
        random_state=42,
        n_jobs=-1
    )
    
    model.fit(X_train)
    
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        joblib.dump(model, save_path)
        logger.info(f"Isolation Forest saved to {save_path}")
    
    global _if_model
    _if_model = model
    
    return model