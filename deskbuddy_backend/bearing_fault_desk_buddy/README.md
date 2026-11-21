# CWRU Bearing Fault Classification — Desk Buddy Backend

A 1D CNN pipeline for classifying vibration windows into four classes:
`Normal`, `Inner Race`, `Ball`, and `Outer Race`.

## Project structure

```text
bearing_fault_desk_buddy/
├── raw_data/                 # Put the four CWRU .mat files here
├── artifacts/                # Model, plots and evaluation outputs
├── arguments.py
├── dataset.py
├── inference.py              # Import this from the Desk Buddy backend
├── main.py
├── model.py
├── preprocess.py
├── test.py
├── train.py
├── visualize.py
└── requirements.txt
```

## 1. Dataset

Put these files in `raw_data/`:

- `97.mat` — Normal
- `105.mat` — Inner Race
- `118.mat` — Ball
- `130.mat` — Outer Race

The MATLAB variable names expected by the pipeline are:
`X097_DE_time`, `X105_DE_time`, `X118_DE_time`, `X130_DE_time`.

## 2. Install and train

Activate your project environment, then run:

```bash
pip install -r requirements.txt
python main.py
```

Optional training settings are defined in `arguments.py`. For example, edit defaults there to change epochs, batch size, learning rate or early stopping patience.

## 3. Outputs

After training, `artifacts/` contains:

- `best_model.pth` — best validation-loss model checkpoint plus class/window metadata
- `training_curves.png` — train/validation loss and accuracy
- `confusion_matrix.png` — test-set confusion matrix
- `class_metrics.png` — per-class precision, recall, F1 and support
- `training_history.json` — epoch-level training history
- `classification_report.json` — detailed test metrics
- `evaluation_summary.json` — compact run summary

## 4. Use from the Industrial Maintenance Desk Buddy backend

Copy `inference.py`, `model.py`, and `artifacts/best_model.pth` into your backend, or keep this folder as a Python package.

```python
from inference import BearingFaultPredictor

predictor = BearingFaultPredictor("artifacts/best_model.pth")

# `vibration_window` must be a 1-D array of exactly 1200 samples.
result = predictor.predict_window(vibration_window)
print(result)
# {
#   "condition": "Normal",
#   "confidence": 0.98,
#   "probabilities": {
#       "Normal": 0.98,
#       "Inner Race": 0.01,
#       "Ball": 0.005,
#       "Outer Race": 0.005
#   }
# }
```

For a longer signal:

```python
result = predictor.predict_signal(raw_vibration_signal, stride=1200)
```

The signal must be sampled at the same rate and acquired using a compatible sensor/setup as the training data. The model was trained on CWRU drive-end vibration signals; it is not automatically calibrated for a different motor, sensor mounting, sampling frequency, or machine.

## Important evaluation limitation

This starter pipeline randomly splits windows from each of four recordings into train/validation/test sets. Windows from the same original recording can therefore appear in multiple splits, making test accuracy optimistic due to recording-level leakage. Treat results as a development baseline, not evidence of industrial reliability. Before deployment, evaluate on completely held-out recordings, loads, bearings and machines; calibrate confidence and define an alert/fallback policy. This model is a decision-support prototype, not a safety system.

## Input contract

- One channel of raw drive-end vibration
- 1200 samples per model window
- Same sampling frequency and signal scaling as the training data
- No normalization is applied in this version; do not add normalization only at inference
