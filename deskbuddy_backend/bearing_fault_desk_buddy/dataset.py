"""Data loaders for the extensive bearing fault CNN."""

from __future__ import annotations

from typing import Optional, Tuple
import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset


def get_dataloaders(
    X: np.ndarray,
    y: np.ndarray,
    opt,
    val_size: float = 0.15,
    test_size: float = 0.15,
    seed: int = 42,
):
    """Build train/val/test DataLoaders with stratified splits and optional
    weighted sampling for imbalanced fault classes.

    X shape: (N, channels, window_size)
    y shape: (N,) integer class labels
    """
    from sklearn.model_selection import train_test_split

    # Split
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, train_size=1.0 - val_size - test_size,
        stratify=y, random_state=seed,
    )
    val_rel = val_size / (val_size + test_size)
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, train_size=val_rel, stratify=y_temp, random_state=seed,
    )

    def to_tensor(arr_x, arr_y):
        tx = torch.as_tensor(arr_x, dtype=torch.float32)
        ty = torch.as_tensor(arr_y, dtype=torch.long)
        return TensorDataset(tx, ty)

    train_ds = to_tensor(X_train, y_train)
    val_ds = to_tensor(X_val, y_val)
    test_ds = to_tensor(X_test, y_test)

    # Weighted sampler for the training set if classes are imbalanced
    sampler = None
    if getattr(opt, "use_weighted_sampler", True):
        class_counts = np.bincount(y_train)
        class_counts[class_counts == 0] = 1
        weights = 1.0 / class_counts[y_train]
        sampler = torch.utils.data.WeightedRandomSampler(
            weights, num_samples=len(weights), replacement=True
        )

    train_dl = DataLoader(
        train_ds, batch_size=opt.batch_size, shuffle=(sampler is None),
        sampler=sampler, num_workers=0, drop_last=True,
    )
    val_dl = DataLoader(
        val_ds, batch_size=opt.batch_size, shuffle=False, num_workers=0,
    )
    test_dl = DataLoader(
        test_ds, batch_size=opt.batch_size, shuffle=False, num_workers=0,
    )

    return train_dl, val_dl, test_dl
