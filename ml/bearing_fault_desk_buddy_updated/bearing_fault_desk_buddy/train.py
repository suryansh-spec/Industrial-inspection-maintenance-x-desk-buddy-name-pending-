"""Enhanced training pipeline for the bearing fault CNN.

Features:
  * Cosine annealing LR schedule with warm restarts
  * Label smoothing
  * Mixup data augmentation
  * Class-balanced sampling / weighted loss for imbalanced fault data
  * Exponential Moving Average (EMA) of model weights
  * Mixed precision (AMP) training on CUDA
  * Robust early stopping with best-state restore
  * Checkpoint saving every N epochs
"""

from __future__ import annotations

import copy
import math
import os
from typing import Any, Dict, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.cuda.amp import GradScaler, autocast
from torch.utils.data import DataLoader, WeightedRandomSampler
from tqdm import tqdm

from model import ExtensiveCNN


class EMA:
    """Exponential Moving Average of model parameters and buffers."""

    def __init__(self, model: nn.Module, decay: float = 0.999):
        self.decay = decay
        self.shadow: Dict[str, torch.Tensor] = {}
        self.backup: Dict[str, torch.Tensor] = {}
        # Track trainable parameters
        for name, param in model.named_parameters():
            if param.requires_grad:
                self.shadow[name] = param.data.clone()
        # Track persistent buffers (e.g. BatchNorm running_mean/running_var)
        for name, buf in model.named_buffers():
            self.shadow[name] = buf.data.clone()

    def update(self, model: nn.Module) -> None:
        for name, param in model.named_parameters():
            if param.requires_grad:
                assert name in self.shadow, f"Missing EMA shadow for {name}"
                new_average = (
                    self.decay * self.shadow[name] + (1.0 - self.decay) * param.data
                )
                self.shadow[name] = new_average.clone()
        for name, buf in model.named_buffers():
            assert name in self.shadow, f"Missing EMA shadow for buffer {name}"
            self.shadow[name] = (
                self.decay * self.shadow[name] + (1.0 - self.decay) * buf.data
            ).clone()

    def apply_shadow(self, model: nn.Module) -> None:
        """Swap in EMA weights (for evaluation)."""
        for name, param in model.named_parameters():
            if param.requires_grad:
                assert name in self.shadow
                self.backup[name] = param.data.clone()
                param.data = self.shadow[name]
        for name, buf in model.named_buffers():
            assert name in self.shadow
            self.backup[name] = buf.data.clone()
            buf.data = self.shadow[name]

    def restore(self, model: nn.Module) -> None:
        """Restore original weights after evaluation."""
        for name, param in model.named_parameters():
            if param.requires_grad:
                assert name in self.backup
                param.data = self.backup[name]
        for name, buf in model.named_buffers():
            assert name in self.backup
            buf.data = self.backup[name]
        self.backup.clear()


def mixup_data(
    x: torch.Tensor, y: torch.Tensor, alpha: float = 0.2
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, float]:
    """Returns mixed inputs, pairs of targets, and lambda."""
    if alpha > 0:
        lam = np.random.beta(alpha, alpha)
    else:
        lam = 1.0
    batch_size = x.size()[0]
    index = torch.randperm(batch_size, device=x.device)
    mixed_x = lam * x + (1 - lam) * x[index, :]
    y_a, y_b = y, y[index]
    return mixed_x, y_a, y_b, lam


def mixup_criterion(criterion, pred, y_a, y_b, lam):
    return lam * criterion(pred, y_a) + (1 - lam) * criterion(pred, y_b)


class LabelSmoothingCrossEntropy(nn.Module):
    """CrossEntropy with label smoothing for better generalization."""

    def __init__(self, smoothing: float = 0.1, weight: Optional[torch.Tensor] = None):
        super().__init__()
        self.smoothing = smoothing
        self.weight = weight

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        n_classes = logits.size(1)
        # Convert hard targets to smoothed one-hot
        with torch.no_grad():
            true_dist = torch.zeros_like(logits)
            true_dist.fill_(self.smoothing / (n_classes - 1))
            true_dist.scatter_(1, target.unsqueeze(1), 1.0 - self.smoothing)
        log_probs = F.log_softmax(logits, dim=1)
        loss = -(true_dist * log_probs).sum(dim=1)
        if self.weight is not None:
            w = self.weight[target]
            loss = loss * w
        return loss.mean()


def compute_class_weights(y: np.ndarray, num_classes: int) -> torch.Tensor:
    """Inverse-frequency class weights for imbalanced fault datasets."""
    counts = np.bincount(y, minlength=num_classes).astype(np.float64)
    counts[counts == 0] = 1.0
    weights = counts.sum() / (num_classes * counts)
    return torch.from_numpy(weights.astype(np.float32))


def train_model(
    opt: Any,
    train_dl: DataLoader,
    valid_dl: DataLoader,
    num_classes: int = 4,
    in_channels: int = 1,
    class_names: Optional[list[str]] = None,
    checkpoint_dir: Optional[str] = None,
) -> Tuple[nn.Module, Dict[str, Any]]:
    """Train the extensive CNN with EMA, mixup, label smoothing, cosine annealing."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = ExtensiveCNN(
        num_classes=num_classes,
        in_channels=in_channels,
        variant=getattr(opt, "variant", "extensive"),
        window_size=getattr(opt, "window_size", 2048),
        dropout=getattr(opt, "dropout", 0.3),
        use_spectral=getattr(opt, "use_spectral", False),
    ).to(device)

    # Class weights from training distribution
    train_labels = []
    for _, y in train_dl:
        train_labels.extend(y.numpy().tolist())
    class_weights = compute_class_weights(np.array(train_labels), num_classes).to(device)

    criterion = LabelSmoothingCrossEntropy(
        smoothing=getattr(opt, "label_smoothing", 0.1), weight=class_weights
    )
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=opt.lr,
        weight_decay=getattr(opt, "weight_decay", 1e-4),
    )

    # Cosine annealing with warm restarts
    scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
        optimizer, T_0=max(5, opt.epochs // 4), T_mult=2
    )

    scaler = GradScaler() if device == "cuda" else None
    ema = EMA(model, decay=getattr(opt, "ema_decay", 0.999))

    history: Dict[str, Any] = {
        "train_loss": [], "valid_loss": [],
        "train_accuracy": [], "valid_accuracy": [],
        "learning_rate": [], "best_epoch": 0,
    }
    best_loss = float("inf")
    patience_count = 0
    best_state = None

    os.makedirs(checkpoint_dir or "checkpoints", exist_ok=True)

    for epoch in tqdm(range(opt.epochs), desc="Training"):
        model.train()
        train_losses, train_correct, train_total = [], 0, 0

        for x, y in train_dl:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad(set_to_none=True)

            # Mixup
            x_mixed, y_a, y_b, lam = mixup_data(x, y, alpha=getattr(opt, "mixup_alpha", 0.2))

            if scaler is not None:
                with autocast():
                    logits = model(x_mixed)
                    loss = mixup_criterion(criterion, logits, y_a, y_b, lam)
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            else:
                logits = model(x_mixed)
                loss = mixup_criterion(criterion, logits, y_a, y_b, lam)
                loss.backward()
                optimizer.step()

            ema.update(model)

            train_losses.append(loss.item())
            # Accuracy computed on clean (unmixed) predictions for monitoring
            with torch.no_grad():
                clean_logits = model(x)
                train_correct += (clean_logits.argmax(1) == y).sum().item()
            train_total += y.size(0)

        model.eval()
        valid_losses, valid_correct, valid_total = [], 0, 0
        # Evaluate with EMA weights
        ema.apply_shadow(model)
        with torch.no_grad():
            for x, y in valid_dl:
                x, y = x.to(device), y.to(device)
                if scaler is not None:
                    with autocast():
                        logits = model(x)
                        loss = criterion(logits, y)
                else:
                    logits = model(x)
                    loss = criterion(logits, y)
                valid_losses.append(loss.item())
                valid_correct += (logits.argmax(1) == y).sum().item()
                valid_total += y.size(0)
        ema.restore(model)

        scheduler.step()
        current_lr = optimizer.param_groups[0]["lr"]

        train_loss = float(np.mean(train_losses))
        valid_loss = float(np.mean(valid_losses))
        history["train_loss"].append(train_loss)
        history["valid_loss"].append(valid_loss)
        history["train_accuracy"].append(100.0 * train_correct / max(train_total, 1))
        history["valid_accuracy"].append(100.0 * valid_correct / max(valid_total, 1))
        history["learning_rate"].append(current_lr)

        # Checkpoint every epoch
        ckpt_path = os.path.join(checkpoint_dir or "checkpoints", f"epoch_{epoch+1}.pth")
        torch.save(
            {
                "epoch": epoch + 1,
                "model_state_dict": model.state_dict(),
                "ema_state": {k: v.clone() for k, v in ema.shadow.items()},
                "optimizer_state_dict": optimizer.state_dict(),
                "scheduler_state_dict": scheduler.state_dict(),
                "valid_loss": valid_loss,
                "valid_accuracy": history["valid_accuracy"][-1],
            },
            ckpt_path,
        )

        if valid_loss < best_loss:
            best_loss = valid_loss
            patience_count = 0
            history["best_epoch"] = epoch + 1
            best_state = copy.deepcopy(model.state_dict())
            best_ema_state = {k: v.clone() for k, v in ema.shadow.items()}
            # Save best
            best_path = os.path.join(checkpoint_dir or "checkpoints", "best_model.pth")
            torch.save(
                {
                    "epoch": epoch + 1,
                    "model_state_dict": best_state,
                    "ema_state_dict": best_ema_state,
                    "class_names": class_names or ["Normal", "Inner Race", "Ball", "Outer Race"],
                    "in_channels": in_channels,
                    "window_size": getattr(opt, "window_size", 2048),
                    "variant": getattr(opt, "variant", "extensive"),
                    "valid_loss": valid_loss,
                    "valid_accuracy": history["valid_accuracy"][-1],
                },
                best_path,
            )
            log_str = f"Epoch {epoch+1}: NEW BEST (val_loss={valid_loss:.4f}, val_acc={history['valid_accuracy'][-1]:.2f}%)"
            tqdm.write(log_str)
        else:
            patience_count += 1
            if patience_count >= opt.early_stop:
                tqdm.write(f"Early stopping at epoch {epoch + 1}")
                break

    if best_state is None:
        raise RuntimeError("Training did not produce a valid checkpoint.")

    # Load best EMA weights for the returned model
    model.load_state_dict(best_ema_state)
    return model, history


def evaluate_model(
    model: nn.Module,
    test_dl: DataLoader,
    num_classes: int = 4,
    class_names: Optional[List[str]] = None,
    device: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate on test set with per-class metrics."""
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    model.eval()

    all_preds = []
    all_targets = []
    all_probs = []

    with torch.no_grad():
        for x, y in test_dl:
            x, y = x.to(device), y.to(device)
            logits = model(x)
            probs = F.softmax(logits, dim=1)
            preds = logits.argmax(1)
            all_preds.extend(preds.cpu().numpy().tolist())
            all_targets.extend(y.cpu().numpy().tolist())
            all_probs.extend(probs.cpu().numpy().tolist())

    all_preds = np.array(all_preds)
    all_targets = np.array(all_targets)
    all_probs = np.array(all_probs)

    accuracy = float((all_preds == all_targets).mean()) * 100.0

    # Per-class recall / precision
    class_metrics = {}
    for cls in range(num_classes):
        tp = int(((all_preds == cls) & (all_targets == cls)).sum())
        fp = int(((all_preds == cls) & (all_targets != cls)).sum())
        fn = int(((all_preds != cls) & (all_targets == cls)).sum())
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        class_metrics[cls] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": int((all_targets == cls).sum()),
        }

    # Confusion matrix
    cm = np.zeros((num_classes, num_classes), dtype=int)
    for t, p in zip(all_targets, all_preds):
        cm[t, p] += 1

    # Classification report for visualization
    from sklearn.metrics import classification_report
    target_names = class_names or [f"class_{i}" for i in range(num_classes)]
    report = classification_report(
        all_targets, all_preds,
        labels=list(range(num_classes)),
        target_names=target_names,
        zero_division=0, output_dict=True
    )

    return {
        "accuracy": round(accuracy, 4),
        "accuracy_pct": round(accuracy, 2),
        "class_metrics": class_metrics,
        "confusion_matrix": cm.tolist(),
        "classification_report": report,
        "probabilities": all_probs,
        "labels": all_targets,
        "predictions": all_preds,
        "num_samples": int(len(all_targets)),
    }
