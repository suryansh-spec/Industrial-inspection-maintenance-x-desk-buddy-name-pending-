
import numpy as np
import torch
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report

def evaluate(test_dl, model, class_names=None):
    device = next(model.parameters()).device
    model.eval()
    preds, labels, probabilities = [], [], []
    with torch.no_grad():
        for x, y in test_dl:
            logits = model(x.to(device))
            probabilities.extend(torch.softmax(logits, dim=1).cpu().numpy().tolist())
            preds.extend(logits.argmax(1).cpu().numpy().tolist())
            labels.extend(y.numpy().tolist())
    preds, labels, probabilities = np.asarray(preds), np.asarray(labels), np.asarray(probabilities)
    if class_names is None:
        class_names = [str(i) for i in range(probabilities.shape[1])]
    acc = accuracy_score(labels, preds) * 100
    cm = confusion_matrix(labels, preds, labels=list(range(len(class_names))))
    report = classification_report(labels, preds, labels=list(range(len(class_names))),
                                   target_names=class_names, zero_division=0, output_dict=True)
    print(f"Test accuracy: {acc:.2f}%")
    print(classification_report(labels, preds, labels=list(range(len(class_names))),
                                target_names=class_names, zero_division=0))
    return {"accuracy": acc, "labels": labels, "predictions": preds,
            "probabilities": probabilities, "confusion_matrix": cm,
            "classification_report": report}
