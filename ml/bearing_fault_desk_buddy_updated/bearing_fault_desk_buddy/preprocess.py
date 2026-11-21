import os
import numpy as np
from scipy.io import loadmat

class CWRUPreprocessor:
    def __init__(self, data_dir, data_list, data_info, condition_list,
                 window_size=1200, num_data=4000):
        self.data_dir = data_dir
        self.data_list = data_list
        self.data_info = data_info
        self.condition_list = condition_list
        self.window_size = window_size
        self.num_data = num_data

    def get_data(self):
        windows, labels = [], []
        for class_idx, filename in enumerate(self.data_list):
            file_path = os.path.join(self.data_dir, filename)
            if not os.path.isfile(file_path):
                raise FileNotFoundError(f"Dataset file not found: {file_path}")

            mat = loadmat(file_path)
            variable = self.data_info[class_idx]
            if variable not in mat:
                candidates = [k for k in mat if k.endswith("_DE_time")]
                raise KeyError(
                    f"MAT variable '{variable}' not found in {filename}. "
                    f"Available drive-end variables: {candidates}"
                )

            signal = np.asarray(mat[variable]).squeeze().astype(np.float32)
            if signal.ndim != 1 or len(signal) < self.window_size:
                raise ValueError(f"Invalid/too-short signal in {filename}: shape={signal.shape}")

            # Select evenly spaced windows from the recording.
            max_start = len(signal) - self.window_size
            starts = np.linspace(0, max_start, num=min(self.num_data, max_start + 1), dtype=int)
            for start in starts:
                windows.append(signal[start:start + self.window_size])
                labels.append(class_idx)

        X = np.stack(windows).astype(np.float32)
        y = np.asarray(labels, dtype=np.int64)
        return X, y
