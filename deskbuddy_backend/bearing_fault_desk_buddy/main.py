"""End-to-end training entry point for the extensive CWRU bearing-fault CNN.

Usage:
    cd ml/bearing_fault_desk_buddy_updated/bearing_fault_desk_buddy
    python main.py --data-dir ../../../datasets/cwru_raw --epochs 60 --variant extensive --window-size 2048 --in-channels 1 --use-spectral

Prerequisites:
    pip install torch torchvision scikit-learn tqdm numpy scipy
    Download CWRU data first:
        python ml/scripts/download_cwru.py --output-dir ml/datasets/cwru_raw --workers 4
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import torch

# Ensure package imports work when run as a script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from preprocess import (
    CWRUPreprocessor,
    MINIMAL_FILES,
    MINIMAL_VARS,
    MINIMAL_CLASSES,
    COMPREHENSIVE_FILES,
    COMPREHENSIVE_CLASSES,
)
from dataset import get_dataloaders
from train import train_model, evaluate_model
from model import create_model


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Train extensive CWRU bearing-fault CNN")
    p.add_argument(
        "--data-dir", required=True,
        help="Directory containing downloaded CWRU .mat files",
    )
    p.add_argument(
        "--output-dir", default="trained_models",
        help="Directory to save model checkpoints and logs",
    )
    p.add_argument(
        "--preset", choices=["minimal", "comprehensive"], default="minimal",
        help="Dataset preset: minimal (4 classes) or comprehensive (many fault/speed variants)",
    )
    p.add_argument("--epochs", type=int, default=60)
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--early-stop", type=int, default=15)
    p.add_argument("--window-size", type=int, default=2048)
    p.add_argument(
        "--in-channels", type=int, choices=[1, 3], default=1,
        help="1 = single-axis DE, 3 = replicated 3-axis",
    )
    p.add_argument(
        "--variant", choices=["light", "extensive"], default="extensive",
        help="Model size variant",
    )
    p.add_argument(
        "--use-spectral", action="store_true",
        help="Add FFT-magnitude spectral branch",
    )
    p.add_argument("--dropout", type=float, default=0.3)
    p.add_argument("--label-smoothing", type=float, default=0.1)
    p.add_argument("--mixup-alpha", type=float, default=0.2)
    p.add_argument("--ema-decay", type=float, default=0.999)
    p.add_argument("--no-weighted-sampler", action="store_true",
                   help="Disable class-weighted sampler")
    p.add_argument("--seed", type=int, default=42)
    return p


def main():
    opt = build_argparser().parse_args()
    np.random.seed(opt.seed)
    torch.manual_seed(opt.seed)

    base = Path(__file__).resolve().parent
    output = base / opt.output_dir
    output.mkdir(parents=True, exist_ok=True)
    ckpt_dir = output / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    # ---- Dataset selection ----
    if opt.preset == "comprehensive":
        files = COMPREHENSIVE_FILES
        classes = COMPREHENSIVE_CLASSES
    else:
        files = MINIMAL_FILES
        classes = MINIMAL_CLASSES

    # MAT variable names: try standard CWRU DE keys, fall back inside preprocessor
    variables = [f"X{f[:-4]}_DE_time" for f in files]

    prep = CWRUPreprocessor(
        data_dir=str(opt.data_dir),
        data_list=files,
        data_info=variables,
        condition_list=classes,
        window_size=opt.window_size,
        num_data=3000,
        overlap=0.5,
        augmentation=True,
        target_channels=opt.in_channels,
    )
    X, y = prep.get_data()
    print(f"Classes: {classes}")
    print(f"Class distribution: {np.bincount(y).tolist()}")

    # ---- DataLoaders ----
    train_dl, val_dl, test_dl = get_dataloaders(
        X, y, opt, seed=opt.seed,
    )
    opt.use_weighted_sampler = not opt.no_weighted_sampler

    # ---- Train ----
    model, history = train_model(
        opt=opt,
        train_dl=train_dl,
        valid_dl=val_dl,
        num_classes=len(classes),
        in_channels=opt.in_channels,
        class_names=classes,
        checkpoint_dir=str(ckpt_dir),
    )

    # ---- Evaluate ----
    metrics = evaluate_model(model, test_dl, num_classes=len(classes))
    print(f"\nTest accuracy: {metrics['accuracy_pct']:.2f}%")
    print("Per-class metrics:")
    for cls, m in metrics["class_metrics"].items():
        print(f"  class {cls}: precision={m['precision']:.3f} recall={m['recall']:.3f} f1={m['f1']:.3f} support={m['support']}")

    # ---- Save final model ----
    model_path = output / "best_model.pth"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "class_names": classes,
            "window_size": opt.window_size,
            "sample_rate_hz": 12000,
            "input_channels": opt.in_channels,
            "architecture": f"ExtensiveCNN-{opt.variant}",
            "variant": opt.variant,
            "use_spectral": opt.use_spectral,
            "dataset": "CWRU",
            "preset": opt.preset,
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
        "class_names": classes,
        "window_size": opt.window_size,
        "sample_rate_hz": 12000,
        "input_channels": opt.in_channels,
        "architecture": f"ExtensiveCNN-{opt.variant}",
        "use_spectral": opt.use_spectral,
        "dataset": "CWRU",
        "preset": opt.preset,
        "class_metrics": metrics["class_metrics"],
        "confusion_matrix": metrics["confusion_matrix"],
    }
    (output / "evaluation_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"\nModel and visualizations saved to: {output}")
    print(f"Best checkpoint: {ckpt_dir / 'best_model.pth'}")


if __name__ == "__main__":
    main()
