"""
Robust CWRU bearing fault training — recording-level split, no leakage.
Optimized for 40 recordings (12k DE): light variant, smaller windows,
conservative LR, aggressive augmentation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import torch
import torch.utils.data as data_utils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from preprocess import CWRUPreprocessor
from train import train_model, evaluate_model
from model import create_model


# ---------------------------------------------------------------------------
# Canonical CWRU 12k Drive End catalog (40 files that downloaded successfully)
# ---------------------------------------------------------------------------
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
CLASS_TO_IDX = {c: i for i, c in enumerate(CLASS_NAMES)}


def build_dataset_from_catalog(
    data_dir: str,
    window_size: int = 1024,
    windows_per_file: int = 2000,
    overlap: float = 0.75,
    target_channels: int = 1,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load all catalog files and build (X, y, recording_ids)."""
    rng = np.random.default_rng(seed)
    all_windows: List[np.ndarray] = []
    all_labels: List[int] = []
    all_recording_ids: List[str] = []

    for file_id, mat_var, fault_type, load_hp, rpm, sr_khz, end in FAULT_CATALOG:
        filename = f"{file_id}.mat"
        file_path = os.path.join(data_dir, filename)
        if not os.path.isfile(file_path):
            print(f"  SKIP {filename}: not found on disk")
            continue

        prep = CWRUPreprocessor(
            data_dir=data_dir,
            data_list=[filename],
            data_info=[mat_var],
            condition_list=[fault_type],
            window_size=window_size,
            num_data=windows_per_file,
            overlap=overlap,
            augmentation=True,
            target_channels=target_channels,
        )
        X_file, y_file = prep.get_data()
        n = len(X_file)

        all_windows.append(X_file)
        all_labels.extend([CLASS_TO_IDX[fault_type]] * n)
        all_recording_ids.extend([file_id] * n)
        print(f"  LOAD {filename} ({fault_type}, {load_hp}hp): {n} windows")

    X = np.concatenate(all_windows, axis=0).astype(np.float32)
    y = np.asarray(all_labels, dtype=np.int64)
    recording_ids = np.asarray(all_recording_ids)

    print(f"\nTotal: {len(X)} windows across {len(FAULT_CATALOG)} recordings")
    print(f"Class distribution: {dict(zip(CLASS_NAMES, np.bincount(y).tolist()))}")
    return X, y, recording_ids


def recording_level_split(
    X: np.ndarray,
    y: np.ndarray,
    recording_ids: np.ndarray,
    test_recording_ids: List[str],
    val_recording_ids: List[str],
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Split so entire recordings are in train OR val OR test — no leakage."""
    test_mask = np.isin(recording_ids, test_recording_ids)
    val_mask = np.isin(recording_ids, val_recording_ids)
    train_mask = ~(test_mask | val_mask)

    X_train, y_train = X[train_mask], y[train_mask]
    X_val, y_val = X[val_mask], y[val_mask]
    X_test, y_test = X[test_mask], y[test_mask]

    print(f"\nTrain: {len(X_train)} windows from {len(set(recording_ids[train_mask]))} recordings")
    print(f"Val  : {len(X_val)} windows from {len(set(recording_ids[val_mask]))} recordings")
    print(f"Test : {len(X_test)} windows from {len(set(recording_ids[test_mask]))} recordings")
    print(f"Train class dist: {dict(zip(CLASS_NAMES, np.bincount(y_train).tolist()))}")
    print(f"Val   class dist: {dict(zip(CLASS_NAMES, np.bincount(y_val).tolist()))}")
    print(f"Test  class dist: {dict(zip(CLASS_NAMES, np.bincount(y_test).tolist()))}")

    return X_train, y_train, X_val, y_val, X_test, y_test


def main():
    parser = argparse.ArgumentParser(description="Train robust CWRU bearing fault model")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--output-dir", default="trained_models_real")
    parser.add_argument("--window-size", type=int, default=1024)
    parser.add_argument("--windows-per-file", type=int, default=2000)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=5e-4)
    parser.add_argument("--variant", choices=["light", "extensive"], default="light")
    parser.add_argument("--use-spectral", action="store_true", default=False)
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    ckpt_dir = output / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Load data
    # ------------------------------------------------------------------
    print("=" * 60)
    print("LOADING CWRU DATASET")
    print("=" * 60)
    X, y, recording_ids = build_dataset_from_catalog(
        data_dir=args.data_dir,
        window_size=args.window_size,
        windows_per_file=args.windows_per_file,
        overlap=0.75,
        target_channels=1,
        seed=args.seed,
    )

    # ------------------------------------------------------------------
    # 2. Recording-level split (NO LEAKAGE)
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("RECORDING-LEVEL SPLIT (no window-level leakage)")
    print("=" * 60)

    # Hold out one recording per class at highest load (3hp) for testing
    test_recording_ids = []
    val_recording_ids = []
    for fault_type in CLASS_NAMES:
        class_rec_ids = [
            fid for fid, _, ft, *_ in FAULT_CATALOG if ft == fault_type
        ]
        load_map = {fid: load for fid, _, _, load, _, _, _ in FAULT_CATALOG}
        # Test = highest load recording
        test_rec = max(class_rec_ids, key=lambda fid: load_map.get(fid, 0))
        test_recording_ids.append(test_rec)
        # Val = second-highest load recording (different from test)
        remaining = [fid for fid in class_rec_ids if fid != test_rec]
        val_rec = max(remaining, key=lambda fid: load_map.get(fid, 0))
        val_recording_ids.append(val_rec)
        print(f"  Test: {test_rec}.mat ({fault_type}, {load_map[test_rec]}hp)")
        print(f"  Val : {val_rec}.mat ({fault_type}, {load_map[val_rec]}hp)")

    X_train, y_train, X_val, y_val, X_test, y_test = recording_level_split(
        X, y, recording_ids, test_recording_ids, val_recording_ids, seed=args.seed
    )

    # ------------------------------------------------------------------
    # 3. Build dataloaders
    # ------------------------------------------------------------------
    def make_dl(Xa, ya, batch_size, shuffle):
        ds = data_utils.TensorDataset(
            torch.as_tensor(Xa, dtype=torch.float32),
            torch.as_tensor(ya, dtype=torch.long),
        )
        return data_utils.DataLoader(ds, batch_size=batch_size, shuffle=shuffle, num_workers=0)

    train_dl = make_dl(X_train, y_train, args.batch_size, shuffle=True)
    val_dl = make_dl(X_val, y_val, args.batch_size, shuffle=False)
    test_dl = make_dl(X_test, y_test, args.batch_size, shuffle=False)

    # ------------------------------------------------------------------
    # 4. Train
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("TRAINING")
    print("=" * 60)

    class Opt:
        pass

    opt = Opt()
    opt.epochs = args.epochs
    opt.lr = args.lr
    opt.weight_decay = 1e-4
    opt.early_stop = 20
    opt.variant = args.variant
    opt.window_size = args.window_size
    opt.dropout = args.dropout
    opt.use_spectral = args.use_spectral
    opt.label_smoothing = 0.05
    opt.mixup_alpha = 0.1
    opt.ema_decay = 0.999

    model, history = train_model(
        opt=opt,
        train_dl=train_dl,
        valid_dl=val_dl,
        num_classes=len(CLASS_NAMES),
        in_channels=1,
        class_names=CLASS_NAMES,
        checkpoint_dir=str(ckpt_dir),
    )

    # ------------------------------------------------------------------
    # 5. Evaluate on held-out test recordings
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("HELD-OUT TEST EVALUATION (no leakage)")
    print("=" * 60)
    metrics = evaluate_model(model, test_dl, num_classes=len(CLASS_NAMES))
    print(f"\nTest accuracy: {metrics['accuracy_pct']:.2f}%")
    print("\nPer-class metrics:")
    for cls_idx, cls_name in enumerate(CLASS_NAMES):
        key = str(cls_idx)
        if key in metrics["class_metrics"]:
            m = metrics["class_metrics"][key]
            print(f"  {cls_name:10s} precision={m['precision']:.3f} "
                  f"recall={m['recall']:.3f} f1={m['f1']:.3f} support={m['support']}")
        else:
            print(f"  {cls_name:10s} no predictions")

    # ------------------------------------------------------------------
    # 6. Save
    # ------------------------------------------------------------------
    model_path = output / "best_model.pth"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "class_names": CLASS_NAMES,
            "window_size": args.window_size,
            "sample_rate_hz": 12000,
            "input_channels": 1,
            "architecture": f"ExtensiveCNN-{args.variant}",
            "variant": args.variant,
            "use_spectral": args.use_spectral,
            "dataset": "CWRU_12k_DE_40files",
            "test_recording_ids": test_recording_ids,
            "val_recording_ids": val_recording_ids,
            "best_epoch": history["best_epoch"],
            "test_accuracy": metrics["accuracy"],
            "history": history,
        },
        model_path,
    )

    summary = {
        "test_accuracy": metrics["accuracy"],
        "accuracy_pct": metrics["accuracy_pct"],
        "best_epoch": history["best_epoch"],
        "class_names": CLASS_NAMES,
        "window_size": args.window_size,
        "sample_rate_hz": 12000,
        "input_channels": 1,
        "architecture": f"ExtensiveCNN-{args.variant}",
        "use_spectral": args.use_spectral,
        "dataset": "CWRU_12k_DE_40files",
        "test_recordings": test_recording_ids,
        "val_recordings": val_recording_ids,
        "class_metrics": metrics["class_metrics"],
        "confusion_matrix": metrics["confusion_matrix"],
        "note": "Recording-level split — no window-level data leakage",
    }
    (output / "evaluation_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"\nSaved model to: {model_path}")
    print(f"Saved summary to: {output / 'evaluation_summary.json'}")


if __name__ == "__main__":
    main()
