"""
Signal Fault Classification Pipeline
CNN-based bearing fault diagnosis on CWRU dataset
"""

__version__ = "1.0.0"
__author__ = "Inspection Desk Buddy Team"

from .model import CNNModel
from .dataset import get_dataloaders, SignalDataset
from .train import train_model, load_model
from .test import evaluate, evaluate_detailed
from .preprocess import CWRUPreprocessor, VibrationPreprocessor
from .visualize import (
    plot_training_curves,
    plot_confusion_matrix,
    plot_per_class_metrics,
    generate_training_report
)

__all__ = [
    "CNNModel",
    "get_dataloaders",
    "SignalDataset",
    "train_model",
    "load_model",
    "evaluate",
    "evaluate_detailed",
    "CWRUPreprocessor",
    "VibrationPreprocessor",
    "plot_training_curves",
    "plot_confusion_matrix",
    "plot_per_class_metrics",
    "generate_training_report",
]