"""
Regenerate research visualizations for the strengthened spectral CWRU model.
Loads the trained model + held-out test data and produces all publication figures.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from preprocess import CWRUPreprocessor
from visualize import (
    save_dataset_visualizations,
    save_training_plots,
    save_evaluation_plots,
)
from train import evaluate_model
from model import ExtensiveCNN
from typing import List, Tuple


# Canonical CWRU 12k Drive End catalog (same as train_real.py)
FAULT_CATALOG: List[Tuple[str, str, str, int, int, int, str]] = [
    # Normal baseline (4 loads, 12k DE)
    ("97",  "X097_DE_time",  "Normal",   0, 1797, 12, "DE"),
    ("98",  "X098_DE_time",  "Normal",   1, 1772, 12, "DE"),
    ("99",  "X099_DE_time",  "Normal",   2, 1750, 12, "DE"),
    ("100", "X100_DE_time",  "Normal",   3, 1730, 12, "DE"),

    # 12k Drive End - Inner Race (3 diameters x 4 loads)
    ("105", "X105_DE_time",  "Inner",    0, 1797, 12, "DE"),
    ("106", "X106_DE_time",  "Inner",    1, 1772, 12, "DE"),
    ("107", "X107_DE_time",  "Inner",    2, 1750, 12, "DE"),
    ("108", "X108_DE_time",  "Inner",    3, 1730, 12, "DE"),
    ("169", "X169_DE_time",  "Inner",    0, 1797, 12, "DE"),
    ("170", "X170_DE_time",  "Inner",    1, 1772, 12, "DE"),
    ("171", "X171_DE_time",  "Inner",    2, 1750, 12, "DE"),
    ("172", "X172_DE_time",  "Inner",    3, 1730, 12, "DE"),
    ("209", "X209_DE_time",  "Inner",    0, 1797, 12, "DE"),
    ("210", "X210_DE_time",  "Inner",    1, 1772, 12, "DE"),
    ("211", "X211_DE_time",  "Inner",    2, 1750, 12, "DE"),
    ("212", "X212_DE_time",  "Inner",    3, 1730, 12, "DE"),

    # 12k Drive End - Ball (3 diameters x 4 loads)
    ("118", "X118_DE_time",  "Ball",     0, 1797, 12, "DE"),
    ("119", "X119_DE_time",  "Ball",     1, 1772, 12, "DE"),
    ("120", "X120_DE_time",  "Ball",     2, 1750, 12, "DE"),
    ("121", "X121_DE_time",  "Ball",     3, 1730, 12, "DE"),
    ("185", "X185_DE_time",  "Ball",     0, 1797, 12, "DE"),
    ("186", "X186_DE_time",  "Ball",     1, 1772, 12, "DE"),
    ("187", "X187_DE_time",  "Ball",     2, 1750, 12, "DE"),
    ("188", "X188_DE_time",  "Ball",     3, 1730, 12, "DE"),
    ("222", "X222_DE_time",  "Ball",     0, 1797, 12, "DE"),
    ("223", "X223_DE_time",  "Ball",     1, 1772, 12, "DE"),
    ("224", "X224_DE_time",  "Ball",     2, 1750, 12, "DE"),
    ("225", "X225_DE_time",  "Ball",     3, 1730, 12, "DE"),

    # 12k Drive End - Outer Race (3 diameters x 4 loads)
    ("130", "X130_DE_time",  "Outer",    0, 1797, 12, "DE"),
    ("131", "X131_DE_time",  "Outer",    1, 1772, 12, "DE"),
    ("132", "X132_DE_time",  "Outer",    2, 1750, 12, "DE"),
    ("133", "X133_DE_time",  "Outer",    3, 1730, 12, "DE"),
    ("197", "X197_DE_time",  "Outer",    0, 1797, 12, "DE"),
    ("198", "X198_DE_time",  "Outer",    1, 1772, 12, "DE"),
    ("199", "X199_DE_time",  "Outer",    2, 1750, 12, "DE"),
    ("200", "X200_DE_time",  "Outer",    3, 1730, 12, "DE"),
    ("234", "X234_DE_time",  "Outer",    0, 1797, 12, "DE"),
    ("235", "X235_DE_time",  "Outer",    1, 1772, 12, "DE"),
    ("236", "X236_DE_time",  "Outer",    2, 1750, 12, "DE"),
    ("237", "X237_DE_time",  "Outer",    3, 1730, 12, "DE"),
]

CLASS_NAMES = ["Normal", "Inner", "Ball", "Outer"]


DATA_DIR = r"E:\VSCODE\multimodel_inspection_desk_buddy\ml\datasets\cwru_full"
MODEL_PATH = r"E:\VSCODE\multimodel_inspection_desk_buddy\ml\bearing_fault_desk_buddy_updated\bearing_fault_desk_buddy\trained_models_spectral\best_model.pth"
OUT_DIR = r"E:\VSCODE\multimodel_inspection_desk_buddy\ml\bearing_fault_desk_buddy_updated\bearing_fault_desk_buddy\trained_models_spectral"


def load_model(path: str, device: str = "cuda"):
    checkpoint = torch.load(path, map_location=device, weights_only=True)
    model = ExtensiveCNN(
        num_classes=len(checkpoint["class_names"]),
        in_channels=int(checkpoint.get("input_channels", 1)),
        variant=checkpoint.get("variant", "light"),
        window_size=int(checkpoint.get("window_size", 1024)),
        use_spectral=bool(checkpoint.get("use_spectral", False)),
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    model.to(device)
    return model, checkpoint


def build_test_data(data_dir: str, window_size: int = 1024, seed: int = 42):
    """Build held-out test data (recordings 100, 108, 121, 133 at 3hp)."""
    rng = np.random.default_rng(seed)
    test_ids = {"100", "108", "121", "133"}
    all_windows: list[np.ndarray] = []
    all_labels: list[int] = []

    for file_id, mat_var, fault_type, load_hp, *_ in FAULT_CATALOG:
        if file_id not in test_ids:
            continue
        filename = f"{file_id}.mat"
        file_path = os.path.join(data_dir, filename)
        if not os.path.isfile(file_path):
            continue

        prep = CWRUPreprocessor(
            data_dir=data_dir,
            data_list=[filename],
            data_info=[mat_var],
            condition_list=[fault_type],
            window_size=window_size,
            num_data=2000,
            overlap=0.0,
            augmentation=False,
            target_channels=1,
        )
        X_file, y_file = prep.get_data()
        all_windows.append(X_file)
        all_labels.extend([CLASS_NAMES.index(fault_type)] * len(X_file))

    X = np.concatenate(all_windows, axis=0).astype(np.float32)
    y = np.asarray(all_labels, dtype=np.int64)
    return X, y


def main():
    out = Path(OUT_DIR)
    out.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Load model + checkpoint info
    # ------------------------------------------------------------------
    model, checkpoint = load_model(MODEL_PATH)
    window_size = int(checkpoint["window_size"])
    class_names = checkpoint["class_names"]
    print(f"Model: {checkpoint['architecture']}, window={window_size}, classes={class_names}")

    # ------------------------------------------------------------------
    # 2. Build test data (held-out recordings)
    # ------------------------------------------------------------------
    X_test, y_test = build_test_data(DATA_DIR, window_size=window_size)
    print(f"Test data: {len(X_test)} windows, class dist: {dict(zip(class_names, np.bincount(y_test).tolist()))}")

    # ------------------------------------------------------------------
    # 3. Dataset visualizations (time domain, FFT, Welch, spectrograms, features)
    # ------------------------------------------------------------------
    print("\nGenerating dataset visualizations (01-09)...")
    save_dataset_visualizations(X_test, y_test, class_names, out, sample_rate=12000)

    # ------------------------------------------------------------------
    # 4. Evaluate model on test data
    # ------------------------------------------------------------------
    print("\nEvaluating model on held-out test recordings...")
    import torch.utils.data as data_utils

    test_ds = data_utils.TensorDataset(
        torch.as_tensor(X_test, dtype=torch.float32),
        torch.as_tensor(y_test, dtype=torch.long),
    )
    test_dl = data_utils.DataLoader(test_ds, batch_size=64, shuffle=False, num_workers=0)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    metrics = evaluate_model(model, test_dl, num_classes=len(class_names), class_names=class_names, device=device)
    print(f"Test accuracy: {metrics['accuracy_pct']:.2f}%")

    # ------------------------------------------------------------------
    # 5. Training plots (history from checkpoint)
    # ------------------------------------------------------------------
    print("\nGenerating training plots (10-11)...")
    history = checkpoint.get("history", {})
    if history:
        save_training_plots(history, out)

    # ------------------------------------------------------------------
    # 6. Evaluation plots (confusion matrix, ROC, PR, confidence)
    # ------------------------------------------------------------------
    print("\nGenerating evaluation plots (12-17)...")
    save_evaluation_plots(metrics, class_names, out)

    print("\nAll visualizations regenerated in:", out)


if __name__ == "__main__":
    main()
