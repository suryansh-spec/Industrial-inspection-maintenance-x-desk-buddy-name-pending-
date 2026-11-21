
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.signal import spectrogram, welch
from scipy.stats import kurtosis, skew
from sklearn.preprocessing import label_binarize
from sklearn.metrics import ConfusionMatrixDisplay, roc_curve, auc, precision_recall_curve, average_precision_score

def save_dataset_visualizations(X, y, class_names, output_dir, sample_rate=12000):
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    X = np.asarray(X); y = np.asarray(y).astype(int); n = len(class_names)
    examples = {c: X[np.flatnonzero(y == c)[0]] for c in range(n) if np.any(y == c)}
    counts = np.bincount(y, minlength=n)

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(class_names, counts); ax.bar_label(bars, padding=3)
    ax.set(title="Dataset class distribution", ylabel="Number of windows"); ax.grid(axis="y", alpha=.25)
    _save(fig, out, "01_class_distribution.png")

    fig, axes = plt.subplots(n, 1, figsize=(12, 2.5*n), squeeze=False)
    for c, ax in enumerate(axes[:, 0]):
        s = examples[c]; t = np.arange(len(s))/sample_rate
        ax.plot(t, s, linewidth=.7); ax.set(title=f"{class_names[c]} — time-domain waveform", xlabel="Time (s)", ylabel="Amplitude"); ax.grid(alpha=.2)
    _save(fig, out, "02_time_domain_waveforms.png")

    fig, axes = plt.subplots(n, 1, figsize=(12, 2.5*n), squeeze=False)
    for c, ax in enumerate(axes[:, 0]):
        s = examples[c] - np.mean(examples[c]); spec = np.abs(np.fft.rfft(s*np.hanning(len(s))))
        freq = np.fft.rfftfreq(len(s), d=1/sample_rate)
        ax.plot(freq, spec, linewidth=.7); ax.set(title=f"{class_names[c]} — FFT spectrum", xlabel="Frequency (Hz)", ylabel="Magnitude"); ax.grid(alpha=.2)
    _save(fig, out, "03_fft_spectra.png")

    fig, axes = plt.subplots(n, 1, figsize=(12, 2.5*n), squeeze=False)
    for c, ax in enumerate(axes[:, 0]):
        f, p = welch(examples[c], fs=sample_rate, nperseg=min(512, len(examples[c])))
        ax.semilogy(f, p+1e-18); ax.set(title=f"{class_names[c]} — Welch PSD", xlabel="Frequency (Hz)", ylabel="Power/Hz"); ax.grid(alpha=.2)
    _save(fig, out, "04_welch_psd.png")

    fig, axes = plt.subplots(n, 1, figsize=(12, 3*n), squeeze=False)
    for c, ax in enumerate(axes[:, 0]):
        f, t, z = spectrogram(examples[c], fs=sample_rate, nperseg=256, noverlap=192)
        mesh = ax.pcolormesh(t, f, 10*np.log10(z+1e-18), shading="auto")
        ax.set(title=f"{class_names[c]} — spectrogram", xlabel="Time (s)", ylabel="Frequency (Hz)")
        fig.colorbar(mesh, ax=ax, label="Power (dB/Hz)")
    _save(fig, out, "05_spectrograms.png")

    names = ["RMS", "Std", "Peak-to-peak", "Kurtosis", "Skewness", "Crest factor"]
    feats = []
    for s in X:
        rms = np.sqrt(np.mean(s.astype(float)**2)); peak = np.max(np.abs(s))
        feats.append([rms, np.std(s), np.ptp(s), kurtosis(s, fisher=True), skew(s), peak/(rms+1e-12)])
    feats = np.asarray(feats)
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    for j, ax in enumerate(axes.flat):
        ax.boxplot([feats[y == c, j] for c in range(n)], labels=class_names, showfliers=False)
        ax.set_title(names[j]); ax.tick_params(axis="x", rotation=20); ax.grid(axis="y", alpha=.2)
    _save(fig, out, "06_feature_boxplots.png")

    means = np.vstack([feats[y == c].mean(axis=0) for c in range(n)])
    z = (means-feats.mean(axis=0))/(feats.std(axis=0)+1e-12)
    fig, ax = plt.subplots(figsize=(10, 5)); im = ax.imshow(z, aspect="auto", cmap="coolwarm")
    ax.set_xticks(range(len(names)), names, rotation=25, ha="right"); ax.set_yticks(range(n), class_names)
    ax.set_title("Class-wise standardized feature profile"); fig.colorbar(im, ax=ax, label="Z-score")
    _save(fig, out, "07_class_feature_profile.png")

    corr = np.corrcoef(feats, rowvar=False)
    fig, ax = plt.subplots(figsize=(8, 7)); im = ax.imshow(corr, vmin=-1, vmax=1, cmap="coolwarm")
    ax.set_xticks(range(len(names)), names, rotation=35, ha="right"); ax.set_yticks(range(len(names)), names)
    ax.set_title("Signal feature correlation"); fig.colorbar(im, ax=ax)
    _save(fig, out, "08_feature_correlation.png")

    fig, ax = plt.subplots(figsize=(9, 6))
    for c in range(n):
        ax.scatter(feats[y == c, 0], feats[y == c, 3], s=8, alpha=.35, label=class_names[c])
    ax.set(title="RMS vs kurtosis", xlabel="RMS", ylabel="Excess kurtosis"); ax.legend(); ax.grid(alpha=.2)
    _save(fig, out, "09_rms_vs_kurtosis.png")

    summary = {"assumed_sample_rate_hz": sample_rate, "window_size": int(X.shape[1]),
               "windows_per_class": {class_names[c]: int(counts[c]) for c in range(n)}}
    (out/"signal_analysis_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

def save_training_plots(history, output_dir):
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    e = range(1, len(history["train_loss"])+1)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    axes[0].plot(e, history["train_loss"], label="Train"); axes[0].plot(e, history["valid_loss"], label="Validation")
    axes[0].set(title="Loss curves", xlabel="Epoch", ylabel="Cross-entropy"); axes[0].legend(); axes[0].grid(alpha=.2)
    axes[1].plot(e, history["train_accuracy"], label="Train"); axes[1].plot(e, history["valid_accuracy"], label="Validation")
    axes[1].set(title="Accuracy curves", xlabel="Epoch", ylabel="Accuracy (%)"); axes[1].set_ylim(0,100); axes[1].legend(); axes[1].grid(alpha=.2)
    _save(fig, out, "10_training_curves.png")
    if "learning_rate" in history:
        fig, ax = plt.subplots(figsize=(8,4)); ax.plot(e, history["learning_rate"], marker="o")
        ax.set(title="Learning-rate schedule", xlabel="Epoch", ylabel="Learning rate"); ax.grid(alpha=.2)
        _save(fig, out, "11_learning_rate.png")
    (out/"training_history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")

def save_evaluation_plots(metrics, class_names, output_dir):
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    n = len(class_names); cm = np.asarray(metrics["confusion_matrix"])
    fig, ax = plt.subplots(figsize=(7,6))
    ConfusionMatrixDisplay(cm, display_labels=class_names).plot(ax=ax, cmap="Blues", values_format="d", colorbar=False)
    ax.set_title(f"Confusion matrix — {metrics['accuracy']:.2f}% accuracy"); _save(fig, out, "12_confusion_matrix.png")

    norm = cm / np.maximum(cm.sum(axis=1, keepdims=True), 1)
    fig, ax = plt.subplots(figsize=(7,6)); im = ax.imshow(norm, vmin=0, vmax=1, cmap="Blues")
    ax.set_xticks(range(n), class_names, rotation=25, ha="right"); ax.set_yticks(range(n), class_names)
    ax.set(xlabel="Predicted", ylabel="Actual", title="Normalized confusion matrix")
    for i in range(n):
        for j in range(n): ax.text(j, i, f"{norm[i,j]:.1%}", ha="center", va="center")
    fig.colorbar(im, ax=ax); _save(fig, out, "13_normalized_confusion_matrix.png")

    report = metrics["classification_report"]
    fig, ax = plt.subplots(figsize=(9,3.5)); ax.axis("off")
    rows = [[c, f'{report[c]["precision"]:.3f}', f'{report[c]["recall"]:.3f}', f'{report[c]["f1-score"]:.3f}', str(report[c]["support"])] for c in class_names]
    table = ax.table(cellText=rows, colLabels=["Class","Precision","Recall","F1","Support"], loc="center", cellLoc="center")
    table.auto_set_font_size(False); table.set_fontsize(10); table.scale(1,1.5); ax.set_title("Per-class test metrics", pad=18)
    _save(fig, out, "14_class_metrics.png")

    probs = np.asarray(metrics.get("probabilities", [])); labels = np.asarray(metrics["labels"]); preds = np.asarray(metrics["predictions"])
    if probs.ndim == 2 and probs.shape[1] == n:
        binary = label_binarize(labels, classes=np.arange(n))
        fig, ax = plt.subplots(figsize=(8,6))
        for c, name in enumerate(class_names):
            fpr, tpr, _ = roc_curve(binary[:,c], probs[:,c]); ax.plot(fpr,tpr,label=f"{name} AUC={auc(fpr,tpr):.3f}")
        ax.plot([0,1],[0,1],"--",label="Chance"); ax.set(title="One-vs-rest ROC curves", xlabel="False positive rate", ylabel="True positive rate")
        ax.legend(); ax.grid(alpha=.2); _save(fig,out,"15_roc_curves.png")

        fig, ax = plt.subplots(figsize=(8,6))
        for c, name in enumerate(class_names):
            p, r, _ = precision_recall_curve(binary[:,c], probs[:,c]); ap = average_precision_score(binary[:,c], probs[:,c])
            ax.plot(r,p,label=f"{name} AP={ap:.3f}")
        ax.set(title="Precision-recall curves", xlabel="Recall", ylabel="Precision"); ax.legend(); ax.grid(alpha=.2)
        _save(fig,out,"16_precision_recall_curves.png")

        conf = probs.max(axis=1); correct = preds == labels
        fig, ax = plt.subplots(figsize=(8,5))
        if correct.any(): ax.hist(conf[correct], bins=20, alpha=.65, label="Correct")
        if (~correct).any(): ax.hist(conf[~correct], bins=20, alpha=.65, label="Incorrect")
        ax.set(title="Prediction confidence: correct vs incorrect", xlabel="Maximum softmax probability", ylabel="Windows")
        ax.legend(); ax.grid(alpha=.2); _save(fig,out,"17_prediction_confidence.png")

    (out/"classification_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

def _save(fig, out, name):
    fig.tight_layout(); fig.savefig(Path(out)/name, dpi=180, bbox_inches="tight"); plt.close(fig)
