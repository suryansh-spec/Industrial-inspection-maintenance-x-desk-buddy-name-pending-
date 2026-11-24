"""Enhanced CWRU preprocessor with multi-axis support, data augmentation,
and overlapping windowing for robust bearing fault classification.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy.io import loadmat


class CWRUPreprocessor:
    """Loads CWRU .mat files and extracts vibration windows.

    Parameters
    ----------
    data_dir : str
        Directory containing the downloaded .mat files.
    data_list : list[str]
        MAT filenames, one per class.
    data_info : list[str]
        MAT variable name for the drive-end (or fan-end) time signal per class.
    condition_list : list[str]
        Human-readable class names.
    window_size : int
        Samples per window (e.g. 1200 at 12 kHz = 0.1 s).
    num_data : int
        Windows per file (before augmentation).
    overlap : float
        Fractional overlap between consecutive windows (0.0 – 0.9).
    augmentation : bool
        If True, apply on-the-fly signal augmentations (jitter, scale, shift).
    target_channels : int
        1 = single-axis (DE only), 3 = synthetic 3-axis from DE+FE pairs.
    """

    def __init__(
        self,
        data_dir: str,
        data_list: List[str],
        data_info: List[str],
        condition_list: List[str],
        window_size: int = 2048,
        num_data: int = 2000,
        overlap: float = 0.5,
        augmentation: bool = True,
        target_channels: int = 1,
    ):
        self.data_dir = data_dir
        self.data_list = data_list
        self.data_info = data_info
        self.condition_list = condition_list
        self.window_size = window_size
        self.num_data = num_data
        self.overlap = overlap
        self.augmentation = augmentation
        self.target_channels = target_channels

    # ------------------------------------------------------------------
    # Signal augmentation
    # ------------------------------------------------------------------
    @staticmethod
    def _augment(signal: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        """Apply random jitter, amplitude scaling, and time shifting."""
        s = signal.copy()
        # Jitter: small random noise
        jitter = rng.normal(0.0, 0.02, size=s.shape)
        s = s + jitter * s.std()
        # Amplitude scaling
        scale = rng.uniform(0.9, 1.1)
        s = s * scale
        # Time shift (circular roll)
        shift = rng.integers(0, s.shape[0])
        s = np.roll(s, shift)
        return s.astype(np.float32)

    # ------------------------------------------------------------------
    # Core loading
    # ------------------------------------------------------------------
    def _extract_variable(self, mat: dict, var_name: str) -> Optional[np.ndarray]:
        """Try the requested variable, then fall back to common DE/FE names."""
        if var_name in mat:
            return np.asarray(mat[var_name]).squeeze().astype(np.float32)
        # Fallbacks commonly found in CWRU MAT files
        for key in mat:
            if key.startswith("__"):
                continue
            if var_name.split("_")[0] in key and key.endswith("_time"):
                return np.asarray(mat[key]).squeeze().astype(np.float32)
        candidates = [k for k in mat if k.endswith("_time") and not k.startswith("__")]
        if candidates:
            return np.asarray(mat[candidates[0]]).squeeze().astype(np.float32)
        return None

    def _windows_from_signal(
        self, signal: np.ndarray, rng: np.random.Generator
    ) -> List[np.ndarray]:
        """Extract possibly overlapping windows from a 1-D signal."""
        signal = signal.astype(np.float32)
        if signal.ndim != 1:
            signal = signal.flatten()
        if len(signal) < self.window_size:
            padded = np.zeros(self.window_size, dtype=np.float32)
            padded[: len(signal)] = signal
            signal = padded

        max_start = len(signal) - self.window_size
        step = max(1, int(self.window_size * (1.0 - self.overlap)))

        if max_start <= 0:
            starts = [0]
        else:
            # Deterministic grid plus random jitter for variety
            n_grid = max(1, max_start // step)
            grid_starts = np.linspace(0, max_start, num=n_grid, dtype=int)
            starts = []
            for gs in grid_starts:
                jitter = int(rng.integers(-step // 2, step // 2 + 1))
                starts.append(int(np.clip(gs + jitter, 0, max_start)))
            # Deduplicate while preserving order
            seen = set()
            uniq = []
            for st in starts:
                if st not in seen:
                    seen.add(st)
                    uniq.append(st)
            starts = uniq[: self.num_data]

        windows = []
        for start in starts:
            w = signal[start : start + self.window_size]
            if len(w) < self.window_size:
                w = np.pad(w, (0, self.window_size - len(w)))
            if self.augmentation:
                w = self._augment(w, rng)
            windows.append(w)
        return windows

    def get_data(
        self,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Return ``(X, y)`` where ``X`` is ``(N, window_size)`` or ``(N, 3, window_size)``."""
        rng = np.random.default_rng(42)
        windows: List[np.ndarray] = []
        labels: List[int] = []

        for class_idx, filename in enumerate(self.data_list):
            file_path = os.path.join(self.data_dir, filename)
            if not os.path.isfile(file_path):
                raise FileNotFoundError(f"Dataset file not found: {file_path}")

            mat = loadmat(file_path)
            signal = self._extract_variable(mat, self.data_info[class_idx])
            if signal is None:
                candidates = [k for k in mat if k.endswith("_time") and not k.startswith("__")]
                raise KeyError(
                    f"MAT variable '{self.data_info[class_idx]}' not found in {filename}. "
                    f"Available time variables: {candidates}"
                )

            file_windows = self._windows_from_signal(signal, rng)
            windows.extend(file_windows)
            labels.extend([class_idx] * len(file_windows))

        X = np.stack(windows).astype(np.float32)
        y = np.asarray(labels, dtype=np.int64)

        # Build 3-channel input if requested (replicate single axis into 3 identical
        # channels so the same model can serve 1-axis and 3-axis deployments).
        if self.target_channels == 3:
            X = np.stack([X, X, X], axis=1)  # (N, 3, window_size)
        else:
            X = X[:, None, :]  # (N, 1, window_size)

        print(f"Prepared {len(X)} windows; input shape: {X.shape}; classes: {self.condition_list}")
        return X, y

    def get_data_splits(
        self,
        train_ratio: float = 0.7,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        seed: int = 42,
    ) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        """Convenience: load and return stratified train/val/test splits."""
        from sklearn.model_selection import train_test_split

        X, y = self.get_data()
        assert abs(train_ratio + val_ratio + test_ratio - 1.0) < 1e-6

        X_train, X_temp, y_train, y_temp = train_test_split(
            X, y, train_size=train_ratio, stratify=y, random_state=seed
        )
        val_rel = val_ratio / (val_ratio + test_ratio)
        X_val, X_test, y_val, y_test = train_test_split(
            X_temp, y_temp, train_size=val_rel, stratify=y_temp, random_state=seed
        )

        return {
            "train": (X_train, y_train),
            "val": (X_val, y_val),
            "test": (X_test, y_test),
        }


# ----------------------------------------------------------------------
# Convenience: canonical CWRU file selections
# ----------------------------------------------------------------------

# Minimal 4-class set (original DeskBuddy configuration)
MINIMAL_FILES = ["97.mat", "105.mat", "118.mat", "130.mat"]
MINIMAL_VARS = ["X097_DE_time", "X105_DE_time", "X118_DE_time", "X130_DE_time"]
MINIMAL_CLASSES = ["Normal", "Inner Race", "Ball", "Outer Race"]

# Full 12k DE set (13 classes: Normal + 3 fault types x 3 diameters)
FULL_12K_DE_FILES = [
    "97.mat",  # Normal 0 hp
    # Inner Race
    "105.mat", "169.mat", "209.mat",
    # Ball
    "118.mat", "185.mat", "222.mat",
    # Outer Race
    "130.mat", "197.mat", "234.mat",
]
FULL_12K_DE_VARS = [
    "X097_DE_time",
    "X105_DE_time", "X169_DE_time", "X209_DE_time",
    "X118_DE_time", "X185_DE_time", "X222_DE_time",
    "X130_DE_time", "X197_DE_time", "X234_DE_time",
]
FULL_12K_DE_CLASSES = [
    "Normal",
    "InnerRace_0.007", "InnerRace_0.014", "InnerRace_0.021",
    "Ball_0.007", "Ball_0.014", "Ball_0.021",
    "OuterRace_0.007", "OuterRace_0.014", "OuterRace_0.021",
]

# Comprehensive set: Normal + 12k DE + 48k DE + 12k FE (multi-load)
COMPREHENSIVE_FILES = [
    # Normal (4 load conditions)
    "97.mat", "98.mat", "99.mat", "100.mat",
    # 12k DE Inner
    "105.mat", "106.mat", "107.mat", "108.mat",
    "169.mat", "170.mat", "171.mat", "172.mat",
    "209.mat", "210.mat", "211.mat", "212.mat",
    # 12k DE Ball
    "118.mat", "119.mat", "120.mat", "121.mat",
    "185.mat", "186.mat", "187.mat", "188.mat",
    "222.mat", "223.mat", "224.mat", "225.mat",
    # 12k DE Outer
    "130.mat", "131.mat", "132.mat", "133.mat",
    "197.mat", "198.mat", "199.mat", "200.mat",
    "234.mat", "235.mat", "236.mat", "237.mat",
    # 48k DE Normal
    "101.mat", "102.mat", "103.mat", "104.mat",
    # 48k DE Inner
    "109.mat", "110.mat", "111.mat", "112.mat",
    "173.mat", "174.mat", "175.mat", "176.mat",
    "213.mat", "214.mat", "215.mat", "216.mat",
    # 48k DE Ball
    "113.mat", "114.mat", "115.mat", "116.mat",
    "189.mat", "190.mat", "191.mat", "192.mat",
    "226.mat", "227.mat", "228.mat", "229.mat",
    # 48k DE Outer
    "127.mat", "128.mat", "129.mat", "134.mat",
    "201.mat", "202.mat", "203.mat", "204.mat",
    "234.mat", "235.mat", "236.mat", "237.mat",
]
COMPREHENSIVE_CLASSES = (
    ["Normal"] +
    [f"12k_DE_Inner_{d}" for d in ("0.007", "0.014", "0.021")] +
    [f"12k_DE_Ball_{d}" for d in ("0.007", "0.014", "0.021")] +
    [f"12k_DE_Outer_{d}" for d in ("0.007", "0.014", "0.021")] +
    [f"48k_DE_Normal_L{l}" for l in range(4)] +
    [f"48k_DE_Inner_{d}" for d in ("0.007", "0.014", "0.021")] +
    [f"48k_DE_Ball_{d}" for d in ("0.007", "0.014", "0.021")] +
    [f"48k_DE_Outer_{d}" for d in ("0.007", "0.014", "0.021")]
)

# NOTE: COMPREHENSIVE_FILES is ordered to match COMPREHENSIVE_CLASSES.
# Each distinct class needs its own MAT variable mapping. Users should
# adjust data_info per file based on the actual MAT key names.
