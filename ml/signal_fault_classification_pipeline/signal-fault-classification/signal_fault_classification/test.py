import torch
import numpy as np
from visualize import (
    plot_confusion_matrix, 
    plot_classification_report, 
    plot_per_class_metrics,
    generate_training_report
)
from train import load_model


def evaluate(test_dl, model, class_names=None, save_dir="reports"):
    """
    Evaluate model on test set with detailed metrics and visualizations.
    
    Args:
        test_dl: Test data loader
        model: Trained model
        class_names: List of class names
        save_dir: Directory to save reports
        
    Returns:
        acc: Test accuracy percentage
        y_true: Ground truth labels
        y_pred: Predicted labels
    """
    if class_names is None:
        class_names = ['Normal', 'Inner Race', 'Ball', 'Outer Race']
    
    model.eval()
    device = next(model.parameters()).device

    preds, labels = [], []

    with torch.no_grad():
        for x, y in test_dl:
            x = x.to(device)
            y = y.to(device)
            y_pred = model(x)
            preds.append(torch.argmax(y_pred, 1).cpu())
            labels.append(y.cpu())

    preds = torch.cat(preds).numpy()
    labels = torch.cat(labels).numpy()
    acc = (preds == labels).mean() * 100

    print(f"\n{'='*50}")
    print(f"TEST RESULTS")
    print(f"{'='*50}")
    print(f"Test Accuracy: {acc:.2f}%")
    print(f"Total Samples: {len(labels)}")
    
    # Generate visualizations
    os.makedirs(save_dir, exist_ok=True)
    plot_confusion_matrix(labels, preds, class_names, 
                          os.path.join(save_dir, "confusion_matrix.png"))
    plot_per_class_metrics(labels, preds, class_names,
                           os.path.join(save_dir, "per_class_metrics.png"))
    plot_classification_report(labels, preds, class_names,
                               os.path.join(save_dir, "classification_report.txt"))
    
    # Save predictions for further analysis
    np.save(os.path.join(save_dir, "predictions.npy"), preds)
    np.save(os.path.join(save_dir, "labels.npy"), labels)
    
    return acc, labels, preds


def evaluate_detailed(test_dl, model, class_names=None, save_dir="reports"):
    """
    Detailed evaluation with per-sample analysis.
    """
    if class_names is None:
        class_names = ['Normal', 'Inner Race', 'Ball', 'Outer Race']
    
    model.eval()
    device = next(model.parameters()).device

    all_preds = []
    all_labels = []
    all_probs = []
    all_logits = []

    with torch.no_grad():
        for x, y in test_dl:
            x = x.to(device)
            y = y.to(device)
            logits = model(x)
            probs = torch.softmax(logits, dim=1)
            y_pred = torch.argmax(logits, 1)
            
            all_preds.append(y_pred.cpu())
            all_labels.append(y.cpu())
            all_probs.append(probs.cpu())
            all_logits.append(logits.cpu())

    preds = torch.cat(all_preds).numpy()
    labels = torch.cat(all_labels).numpy()
    probs = torch.cat(all_probs).numpy()
    logits = torch.cat(all_logits).numpy()
    
    acc = (preds == labels).mean() * 100
    
    # Per-class accuracy
    print(f"\nPer-Class Accuracy:")
    for cls_idx, cls_name in enumerate(class_names):
        cls_mask = labels == cls_idx
        if cls_mask.sum() > 0:
            cls_acc = (preds[cls_mask] == labels[cls_mask]).mean() * 100
            print(f"  {cls_name}: {cls_acc:.2f}% ({cls_mask.sum()} samples)")
    
    # Confidence analysis
    max_probs = probs.max(axis=1)
    print(f"\nPrediction Confidence:")
    print(f"  Mean: {max_probs.mean():.4f}")
    print(f"  Min: {max_probs.min():.4f}")
    print(f"  Std: {max_probs.std():.4f}")
    
    # Low confidence predictions
    low_conf = max_probs < 0.7
    if low_conf.any():
        print(f"  Low confidence (<0.7): {low_conf.sum()} samples ({low_conf.mean()*100:.1f}%)")
    
    return {
        'accuracy': acc,
        'predictions': preds,
        'labels': labels,
        'probabilities': probs,
        'logits': logits,
        'class_names': class_names
    }


if __name__ == "__main__":
    # Test with dummy data
    import os
    os.makedirs("demo_reports", exist_ok=True)
    
    np.random.seed(42)
    y_true = np.random.randint(0, 4, 1000)
    y_pred = np.random.randint(0, 4, 1000)
    # Make predictions somewhat correlated
    for i in range(len(y_pred)):
        if np.random.rand() < 0.8:
            y_pred[i] = y_true[i]
    
    plot_confusion_matrix(y_true, y_pred, save_path="demo_reports/confusion_matrix.png")
    plot_per_class_metrics(y_true, y_pred, save_path="demo_reports/per_class_metrics.png")
    plot_classification_report(y_true, y_pred, save_path="demo_reports/classification_report.txt")
    print("Demo visualizations generated in demo_reports/")