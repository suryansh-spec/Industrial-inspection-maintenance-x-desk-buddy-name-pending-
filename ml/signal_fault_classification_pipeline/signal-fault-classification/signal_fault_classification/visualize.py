"""
Visualization utilities for the signal fault classification pipeline.
Generates training curves, confusion matrices, and classification reports.
"""

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for headless environments
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import torch
import json
import os
from sklearn.metrics import confusion_matrix, classification_report
from typing import List, Dict, Optional

# Set style
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_palette("husl")


def plot_training_curves(result_dict: Dict, save_path: str = "training_curves.png"):
    """
    Plot training and validation loss curves.
    
    Args:
        result_dict: Dictionary containing 'train_loss', 'valid_loss', 'stop_point'
        save_path: Path to save the plot
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    
    epochs = range(1, len(result_dict['train_loss']) + 1)
    stop_point = result_dict.get('stop_point', len(result_dict['train_loss']))
    
    # Loss curves
    ax1.plot(epochs, result_dict['train_loss'], 'b-', label='Training Loss', linewidth=2)
    ax1.plot(epochs, result_dict['valid_loss'], 'r-', label='Validation Loss', linewidth=2)
    ax1.axvline(x=stop_point, color='green', linestyle='--', label=f'Best Epoch ({stop_point})')
    ax1.set_xlabel('Epoch', fontsize=12)
    ax1.set_ylabel('Loss', fontsize=12)
    ax1.set_title('Training & Validation Loss', fontsize=14, fontweight='bold')
    ax1.legend(fontsize=11)
    ax1.grid(True, alpha=0.3)
    
    # Log scale for loss
    ax2.semilogy(epochs, result_dict['train_loss'], 'b-', label='Training Loss', linewidth=2)
    ax2.semilogy(epochs, result_dict['valid_loss'], 'r-', label='Validation Loss', linewidth=2)
    ax2.axvline(x=stop_point, color='green', linestyle='--', label=f'Best Epoch ({stop_point})')
    ax2.set_xlabel('Epoch', fontsize=12)
    ax2.set_ylabel('Loss (log scale)', fontsize=12)
    ax2.set_title('Training & Validation Loss (Log Scale)', fontsize=14, fontweight='bold')
    ax2.legend(fontsize=11)
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ Training curves saved to {save_path}")


def plot_confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray, 
                          class_names: List[str] = None,
                          save_path: str = "confusion_matrix.png",
                          normalize: bool = True):
    """
    Plot confusion matrix with seaborn heatmap.
    
    Args:
        y_true: Ground truth labels
        y_pred: Predicted labels
        class_names: List of class names
        save_path: Path to save the plot
        normalize: Whether to normalize rows
    """
    if class_names is None:
        class_names = ['Normal', 'Inner Race', 'Ball', 'Outer Race']
    
    cm = confusion_matrix(y_true, y_pred)
    if normalize:
        cm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
        fmt = '.2f'
        title = 'Normalized Confusion Matrix'
    else:
        fmt = 'd'
        title = 'Confusion Matrix'
    
    plt.figure(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt=fmt, cmap='Blues', 
                xticklabels=class_names, yticklabels=class_names,
                cbar_kws={'label': 'Proportion' if normalize else 'Count'})
    plt.title(title, fontsize=14, fontweight='bold')
    plt.xlabel('Predicted Label', fontsize=12)
    plt.ylabel('True Label', fontsize=12)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ Confusion matrix saved to {save_path}")
    
    return cm


def plot_classification_report(y_true: np.ndarray, y_pred: np.ndarray,
                                class_names: List[str] = None,
                                save_path: str = "classification_report.txt"):
    """
    Generate and save detailed classification report.
    
    Args:
        y_true: Ground truth labels
        y_pred: Predicted labels
        class_names: List of class names
        save_path: Path to save the report
    """
    if class_names is None:
        class_names = ['Normal', 'Inner Race', 'Ball', 'Outer Race']
    
    report = classification_report(y_true, y_pred, target_names=class_names, digits=4)
    
    with open(save_path, 'w') as f:
        f.write(report)
    
    print(f"✅ Classification report saved to {save_path}")
    print(report)
    
    return report


def plot_per_class_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                           class_names: List[str] = None,
                           save_path: str = "per_class_metrics.png"):
    """
    Plot per-class precision, recall, F1-score.
    """
    if class_names is None:
        class_names = ['Normal', 'Inner Race', 'Ball', 'Outer Race']
    
    report_dict = classification_report(y_true, y_pred, target_names=class_names, 
                                        output_dict=True, zero_division=0)
    
    metrics = ['precision', 'recall', 'f1-score']
    x = np.arange(len(class_names))
    width = 0.25
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    for i, metric in enumerate(metrics):
        values = [report_dict[cls][metric] for cls in class_names]
        ax.bar(x + i * width, values, width, label=metric.capitalize(), alpha=0.8)
    
    ax.set_xlabel('Class', fontsize=12)
    ax.set_ylabel('Score', fontsize=12)
    ax.set_title('Per-Class Precision, Recall, F1-Score', fontsize=14, fontweight='bold')
    ax.set_xticks(x + width)
    ax.set_xticklabels(class_names)
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ Per-class metrics saved to {save_path}")


def generate_training_report(result_dict: Dict, y_true: np.ndarray, y_pred: np.ndarray,
                             class_names: List[str] = None,
                             output_dir: str = "reports",
                             model_info: Dict = None):
    """
    Generate complete training report with all visualizations.
    
    Args:
        result_dict: Training results dictionary
        y_true: Ground truth test labels
        y_pred: Predicted test labels
        class_names: Class names
        output_dir: Directory to save reports
        model_info: Additional model info (architecture, params, etc.)
    """
    if class_names is None:
        class_names = ['Normal', 'Inner Race', 'Ball', 'Outer Race']
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate all visualizations
    plot_training_curves(result_dict, os.path.join(output_dir, "training_curves.png"))
    plot_confusion_matrix(y_true, y_pred, class_names, 
                          os.path.join(output_dir, "confusion_matrix.png"))
    plot_per_class_metrics(y_true, y_pred, class_names,
                           os.path.join(output_dir, "per_class_metrics.png"))
    plot_classification_report(y_true, y_pred, class_names,
                               os.path.join(output_dir, "classification_report.txt"))
    
    # Save training history as JSON
    history = {
        'train_loss': result_dict['train_loss'],
        'valid_loss': result_dict['valid_loss'],
        'best_epoch': result_dict.get('stop_point', len(result_dict['train_loss'])),
        'final_train_loss': result_dict['train_loss'][-1] if result_dict['train_loss'] else None,
        'final_valid_loss': result_dict['valid_loss'][-1] if result_dict['valid_loss'] else None,
    }
    
    with open(os.path.join(output_dir, "training_history.json"), 'w') as f:
        json.dump(history, f, indent=2)
    
    # Generate summary report
    cm = confusion_matrix(y_true, y_pred)
    accuracy = (y_true == y_pred).mean() * 100
    
    summary = {
        'test_accuracy': accuracy,
        'best_epoch': result_dict.get('stop_point', len(result_dict['train_loss'])),
        'total_epochs_trained': len(result_dict['train_loss']),
        'final_train_loss': history['final_train_loss'],
        'final_valid_loss': history['final_valid_loss'],
        'confusion_matrix': cm.tolist(),
        'class_names': class_names,
        'model_info': model_info or {}
    }
    
    with open(os.path.join(output_dir, "summary.json"), 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n{'='*50}")
    print(f"TRAINING REPORT GENERATED: {output_dir}")
    print(f"{'='*50}")
    print(f"Test Accuracy: {accuracy:.2f}%")
    print(f"Best Epoch: {summary['best_epoch']}")
    print(f"Total Epochs: {summary['total_epochs_trained']}")
    print(f"Files generated:")
    for f in os.listdir(output_dir):
        print(f"  - {f}")
    
    return summary


def plot_signal_samples(X: np.ndarray, y: np.ndarray, class_names: List[str] = None,
                        n_samples: int = 4, save_path: str = "signal_samples.png"):
    """
    Plot raw signal samples for each class.
    """
    if class_names is None:
        class_names = ['Normal', 'Inner Race', 'Ball', 'Outer Race']
    
    num_classes = len(class_names)
    fig, axes = plt.subplots(num_classes, n_samples, figsize=(4*n_samples, 3*num_classes))
    
    for cls_idx in range(num_classes):
        cls_indices = np.where(y == cls_idx)[0]
        if len(cls_indices) == 0:
            continue
        sample_indices = np.random.choice(cls_indices, min(n_samples, len(cls_indices)), replace=False)
        
        for sample_idx, idx in enumerate(sample_indices):
            ax = axes[cls_idx, sample_idx] if num_classes > 1 else axes[sample_idx]
            ax.plot(X[idx])
            ax.set_title(f"{class_names[cls_idx]} (sample {idx})")
            ax.grid(True, alpha=0.3)
            ax.set_xlabel("Time")
            ax.set_ylabel("Amplitude")
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ Signal samples saved to {save_path}")


def plot_learning_rate_schedule(lr_schedule: List[float], save_path: str = "lr_schedule.png"):
    """Plot learning rate schedule."""
    plt.figure(figsize=(10, 4))
    plt.plot(lr_schedule)
    plt.xlabel('Epoch')
    plt.ylabel('Learning Rate')
    plt.title('Learning Rate Schedule')
    plt.yscale('log')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()


if __name__ == "__main__":
    # Demo with dummy data
    np.random.seed(42)
    y_true = np.random.randint(0, 4, 1000)
    y_pred = np.random.randint(0, 4, 1000)
    
    # Make predictions somewhat correlated with truth
    for i in range(len(y_pred)):
        if np.random.rand() < 0.8:
            y_pred[i] = y_true[i]
    
    result_dict = {
        'train_loss': [0.8, 0.6, 0.45, 0.35, 0.3, 0.28, 0.27, 0.26, 0.26, 0.27],
        'valid_loss': [0.75, 0.55, 0.4, 0.32, 0.28, 0.26, 0.26, 0.27, 0.28, 0.3],
        'stop_point': 7
    }
    
    os.makedirs("demo_reports", exist_ok=True)
    generate_training_report(result_dict, y_true, y_pred, output_dir="demo_reports")