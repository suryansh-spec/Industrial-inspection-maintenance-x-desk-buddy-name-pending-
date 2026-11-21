
from pathlib import Path
import json
import numpy as np
import torch
from arguments import get_args
from dataset import get_dataloaders
from train import train_model
from test import evaluate
from preprocess import CWRUPreprocessor
from visualize import save_dataset_visualizations, save_training_plots, save_evaluation_plots

def main():
    opt = get_args()
    base = Path(__file__).resolve().parent
    output = base / opt.output_dir
    output.mkdir(parents=True, exist_ok=True)
    classes = ["Normal", "Inner Race", "Ball", "Outer Race"]
    files = ["97.mat", "105.mat", "118.mat", "130.mat"]
    variables = ["X097_DE_time", "X105_DE_time", "X118_DE_time", "X130_DE_time"]
    sample_rate, window_size = 12000, 1200

    prep = CWRUPreprocessor(str(base/"raw_data"), files, variables, classes,
                            window_size=window_size, num_data=4000)
    X, y = prep.get_data()
    print(f"Prepared {len(X)} windows; input shape: {X.shape}")

    save_dataset_visualizations(X, y, classes, output, sample_rate)
    Y = np.eye(len(classes), dtype=np.float32)[y]
    train_dl, valid_dl, test_dl = get_dataloaders(X, Y, opt)
    model, history = train_model(opt, train_dl, valid_dl, num_classes=len(classes))
    metrics = evaluate(test_dl, model, classes)
    save_training_plots(history, output)
    save_evaluation_plots(metrics, classes, output)

    torch.save({
        "model_state_dict": model.state_dict(), "class_names": classes,
        "window_size": window_size, "sample_rate_hz": sample_rate,
        "input_channels": 1, "architecture": "CNNModel-1D",
        "dataset": "CWRU", "best_epoch": history["best_epoch"],
        "test_accuracy": metrics["accuracy"]
    }, output/"best_model.pth")

    summary = {"test_accuracy": metrics["accuracy"], "best_epoch": history["best_epoch"],
               "class_names": classes, "window_size": window_size,
               "sample_rate_hz": sample_rate}
    (output/"evaluation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Model and visualizations saved to: {output}")

if __name__ == "__main__":
    main()
