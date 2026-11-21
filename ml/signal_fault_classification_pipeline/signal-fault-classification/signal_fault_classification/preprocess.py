import numpy as np
import os
from scipy.io import loadmat
from typing import Tuple, List, Optional
from visualize import plot_signal_samples


class CWRUPreprocessor:
    """
    Preprocessor for CWRU Bearing Fault Dataset.
    
    Converts raw .mat files into sliding window segments for supervised classification.
    
    Dataset: Case Western Reserve University Bearing Data Center
    Classes: Normal (0), Inner Race (1), Ball (2), Outer Race (3)
    """
    
    def __init__(self, data_dir: str, data_list: List[str], data_info: List[str],
                 condition_list: List[str], window_size: int = 1200, num_data: int = 4000):
        """
        Initialize preprocessor.
        
        Args:
            data_dir: Directory containing .mat files
            data_list: List of .mat filenames
            data_info: List of variable names inside .mat files
            condition_list: List of class labels
            window_size: Size of sliding window (default: 1200)
            num_data: Number of samples per class (default: 4000)
        """
        self.data_dir = data_dir
        self.data_list = data_list
        self.data_info = data_info
        self.condition_list = condition_list
        self.window_size = window_size
        self.num_data = num_data
        
        # Validate inputs
        assert len(data_list) == len(data_info) == len(condition_list), \
            "data_list, data_info, and condition_list must have same length"
        
    def get_data(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Process all .mat files and return features and labels.
        
        Returns:
            X_data: Shape (num_classes * num_data, window_size)
            Y_data: One-hot encoded labels (num_classes * num_data, num_classes)
        """
        num_classes = len(self.data_list)
        X_data = np.zeros((self.num_data * num_classes, self.window_size), dtype=np.float32)
        Y_data = np.zeros((self.num_data * num_classes, num_classes), dtype=np.float32)
        
        print(f"Processing {num_classes} classes, {self.num_data} samples each...")
        
        for k, filename in enumerate(self.data_list):
            filepath = os.path.join(self.data_dir, filename)
            
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"File not found: {filepath}")
            
            # Load .mat file
            mat_data = loadmat(filepath)
            
            if self.data_info[k] not in mat_data:
                available_keys = [k for k in mat_data.keys() if not k.startswith('__')]
                raise KeyError(f"Key '{self.data_info[k]}' not found in {filename}. "
                               f"Available keys: {available_keys}")
            
            signal = mat_data[self.data_info[k]].squeeze()
            
            # Ensure signal is 1D
            if signal.ndim > 1:
                signal = signal.flatten()
            
            print(f"  Class {k} ({self.condition_list[k]}): {filename} "
                  f"[{self.data_info[k]}] - Signal length: {len(signal)}")
            
            # Generate sliding window indices
            step = max(1, int((len(signal) - self.window_size) / self.num_data))
            max_start = len(signal) - self.window_size
            
            if max_start < 0:
                raise ValueError(f"Signal too short ({len(signal)}) for window_size ({self.window_size}) "
                               f"in {filename}")
            
            ix = list(range(0, max_start, step))[:self.num_data]
            
            if len(ix) < self.num_data:
                # If not enough windows, pad by repeating
                print(f"    Warning: Only {len(ix)} windows available, "
                      f"need {self.num_data}. Padding with last window.")
                ix = ix + [ix[-1]] * (self.num_data - len(ix))
            
            # Extract windows
            for i, idx in enumerate(ix):
                X_data[i + k * self.num_data] = signal[idx:idx + self.window_size].astype(np.float32)
                Y_data[i + k * self.num_data] = np.eye(len(self.condition_list))[k]
        
        print(f"Total samples: {len(X_data)}")
        print(f"X shape: {X_data.shape}, Y shape: {Y_data.shape}")
        
        return X_data, Y_data
    
    def visualize_samples(self, X: np.ndarray, Y: np.ndarray, 
                          class_names: List[str] = None, 
                          save_path: str = "signal_samples.png",
                          n_samples: int = 4):
        """Visualize signal samples for each class."""
        if class_names is None:
            class_names = self.condition_list
        plot_signal_samples(X, Y.argmax(axis=1), class_names, n_samples, save_path)


class VibrationPreprocessor:
    """
    Preprocessor for custom vibration data (e.g., from ADXL345 sensor).
    
    Converts raw vibration signals into windows suitable for the trained model.
    """
    
    def __init__(self, window_size: int = 1200, sampling_rate: int = 1000):
        """
        Args:
            window_size: Number of samples per window (default: 1200 = 1.2s at 1kHz)
            sampling_rate: Sampling rate in Hz (default: 1000 Hz)
        """
        self.window_size = window_size
        self.sampling_rate = sampling_rate
    
    def process_signal(self, signal: np.ndarray, 
                       overlap: float = 0.5) -> np.ndarray:
        """
        Convert continuous signal into overlapping windows.
        
        Args:
            signal: 1D array of vibration data
            overlap: Overlap fraction between windows (0.0 to 1.0)
            
        Returns:
            windows: Shape (num_windows, window_size)
        """
        signal = np.asarray(signal, dtype=np.float32).squeeze()
        
        if signal.ndim != 1:
            raise ValueError("Signal must be 1D array")
        
        if len(signal) < self.window_size:
            # Pad if too short
            padded = np.zeros(self.window_size, dtype=np.float32)
            padded[:len(signal)] = signal
            return padded.reshape(1, -1)
        
        step = int(self.window_size * (1 - overlap))
        step = max(1, step)
        
        windows = []
        for i in range(0, len(signal) - self.window_size + 1, step):
            windows.append(signal[i:i + self.window_size])
        
        return np.array(windows, dtype=np.float32)
    
    def extract_features(self, signal: np.ndarray) -> dict:
        """
        Extract statistical features from vibration signal.
        
        Returns:
            Dictionary of features matching backend expectations
        """
        signal = np.asarray(signal, dtype=np.float32).squeeze()
        
        # Time domain features
        rms = np.sqrt(np.mean(signal**2))
        peak = np.max(np.abs(signal))
        p2p = signal.max() - signal.min()
        crest = peak / rms if rms > 1e-12 else 0.0
        
        # Kurtosis
        mean_sig = signal.mean()
        var = signal.var()
        kurtosis = np.mean((signal - mean_sig)**4) / var**2 if var > 1e-12 else 0.0
        
        # Frequency domain
        n = len(signal)
        fft_vals = np.fft.rfft(signal)
        freqs = np.fft.rfftfreq(n, 1/self.sampling_rate)
        mag = np.abs(fft_vals)
        
        # Dominant frequency (ignore DC)
        if len(mag) > 1:
            dom_idx = np.argmax(mag[1:]) + 1
            dominant_freq = freqs[dom_idx]
        else:
            dominant_freq = 0.0
        
        return {
            'rms': float(rms),
            'peak': float(peak),
            'p2p': float(p2p),
            'crest': float(crest),
            'kurtosis': float(kurtosis),
            'dominant_freq_hz': float(dominant_freq)
        }


if __name__ == "__main__":
    # Test with dummy data
    import tempfile
    import scipy.io as sio
    
    # Create dummy .mat files for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, (fname, varname, label) in enumerate([
            ('97.mat', 'X097_DE_time', 'Normal'),
            ('105.mat', 'X105_DE_time', 'Inner Race'),
            ('118.mat', 'X118_DE_time', 'Ball'),
            ('130.mat', 'X130_DE_time', 'Outer Race')
        ]):
            # Generate synthetic vibration signal
            t = np.arange(120000)
            signal = np.sin(2 * np.pi * 50 * t / 12000)  # 50 Hz base
            signal += 0.5 * np.sin(2 * np.pi * 120 * t / 12000)  # 120 Hz harmonic
            signal += 0.1 * np.random.randn(len(t))  # Noise
            sio.savemat(os.path.join(tmpdir, fname), {varname: signal.reshape(-1, 1)})
        
        # Test preprocessor
        preprocessor = CWRUPreprocessor(
            data_dir=tmpdir,
            data_list=['97.mat', '105.mat', '118.mat', '130.mat'],
            data_info=['X097_DE_time', 'X105_DE_time', 'X118_DE_time', 'X130_DE_time'],
            condition_list=['Normal', 'Inner Race', 'Ball', 'Outer Race'],
            window_size=1200,
            num_data=100
        )
        
        X, Y = preprocessor.get_data()
        print(f"\nX shape: {X.shape}, Y shape: {Y.shape}")
        print(f"Classes: {Y.sum(axis=0)}")