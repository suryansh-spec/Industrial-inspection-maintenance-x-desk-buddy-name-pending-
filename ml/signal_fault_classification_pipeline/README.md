# Signal Fault Classification Pipeline

CNN-based bearing fault diagnosis on CWRU dataset with complete training, evaluation, and visualization pipeline.

## 📁 Project Structure

```
signal-fault-classification/
├── main.py                 # Main entry point (CLI)
├── train_pipeline.py       # Complete training pipeline script
├── test_pipeline.py        # Test suite
├── generate_report.py      # HTML report generator
├── arguments.py            # Command-line arguments
├── dataset.py              # Data loaders
├── model.py                # CNN model definition
├── train.py                # Training logic with early stopping
├── test.py                 # Evaluation with visualizations
├── preprocess.py           # CWRU data preprocessing + vibration features
├── visualize.py            # Plotting utilities (curves, confusion matrix, etc.)
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Download CWRU Dataset
Download `.mat` files from [CWRU Bearing Data Center](https://engineering.case.edu/bearingdatacenter/download-data-file) and place in `./data/`:
```
data/
├── 97.mat     # Normal (0)
├── 105.mat    # Inner Race fault (1)
├── 118.mat    # Ball fault (2)
├── 130.mat    # Outer Race fault (3)
```

### 3. Run Training
```bash
# Basic training
python main.py

# Custom parameters
python main.py --epochs 100 --lr 1e-3 --batch_size 128

# Evaluate existing model
python main.py --eval_only --model_path models/cnn_model.pth
```

### 4. Run Tests
```bash
python test_pipeline.py
```

### 5. Generate HTML Report
```bash
python generate_report.py
# Opens reports/training_report.html
```

## 🎯 CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--data_dir` | `./data` | Directory with `.mat` files |
| `--data_list` | `['97.mat','105.mat','118.mat','130.mat']` | Mat filenames |
| `--data_info` | `['X097_DE_time',...]` | Variable names in .mat |
| `--condition_list` | `['Normal','IR','B','OR']` | Class labels |
| `--window_size` | `1200` | Sliding window size |
| `--num_data` | `4000` | Samples per class |
| `--epochs` | `50` | Training epochs |
| `--lr` | `1e-4` | Learning rate |
| `--lamda` | `0.97` | LR decay factor |
| `--early_stop` | `20` | Early stopping patience |
| `--train_size` | `0.8` | Train/val/test split |
| `--batch_size` | `64` | Batch size |
| `--model_path` | `models/cnn_model.pth` | Model save/load path |
| `--eval_only` | `False` | Evaluate only (no training) |
| `--detailed_eval` | `False` | Run detailed evaluation |

## 🏗️ Model Architecture

```
Input (1, 1200)
    │
    ├─ Conv1d(1→16, k=3, p=1) → BatchNorm → ReLU → MaxPool(2)
    │   Output: (16, 600)
    │
    ├─ Conv1d(16→32, k=3, p=1) → BatchNorm → ReLU → MaxPool(2)
    │   Output: (32, 300)
    │
    ├─ Conv1d(32→64, k=3, p=1) → BatchNorm → ReLU → MaxPool(2)
    │   Output: (64, 150)
    │
    ├─ Flatten → (9600)
    │
    ├─ Linear(9600→1000) → BatchNorm → ReLU
    ├─ Linear(1000→100)  → BatchNorm → ReLU
    └─ Linear(100→4) → Output (4 classes)
```

- **Parameters**: ~620K
- **Input**: Single-channel vibration signal (1200 samples = 1.2s at 1kHz)
- **Output**: 4 classes (Normal, Inner Race, Ball, Outer Race)

## 📊 Outputs

After training, the following are generated:

```
models/
├── cnn_model.pth              # Trained model checkpoint
├── training_history.json      # Loss curves, LR schedule

reports/
├── training_curves.png        # Loss vs epoch
├── confusion_matrix.png       # Normalized confusion matrix
├── per_class_metrics.png      # Precision/Recall/F1 per class
├── signal_samples.png         # Raw signal samples per class
├── classification_report.txt  # sklearn classification report
├── training_report.html       # Complete HTML report
└── summary.json               # Summary metrics
```

## 🔧 Integration with Backend

The trained model integrates with the FastAPI backend in `backend/app/pipelines/vibrations.py`:

```python
from app.pipelines.vibrations import analyze, analyze_vibration_cnn

# Auto-detect method (CNN first, fallback to traditional)
result = analyze(x, y, z, fs=1000, method="auto")

# CNN only
result = analyze_vibration_cnn(x, y, z, fs=1000)

# Traditional features only
result = analyze_vibration_traditional(x, y, z, fs=1000)
```

## 📈 Visualizations

| Visualization | Description |
|---------------|-------------|
| Training Curves | Loss vs epoch (linear + log scale) |
| Confusion Matrix | Normalized, per-class |
| Per-Class Metrics | Precision/Recall/F1 bars |
| Signal Samples | 4 raw samples per class |
| Classification Report | Detailed sklearn report |

## 🎯 Classes

| Index | Label | Description |
|-------|-------|-------------|
| 0 | Normal | Healthy bearing |
| 1 | Inner Race | Inner race fault |
| 2 | Ball | Ball/rolling element fault |
| 3 | Outer Race | Outer race fault |

## 📦 Model Export for Edge Deployment

```python
import torch

# Export to ONNX
model = CNNModel()
checkpoint = torch.load('models/cnn_model.pth', map_location='cpu')
model.load_state_dict(checkpoint['model_state_dict'])
model.eval()

dummy = torch.randn(1, 1, 1200)
torch.onnx.export(model, dummy, 'models/cnn_model.onnx',
                  input_names=['input'], output_names=['output'],
                  dynamic_axes={'input': {0: 'batch'}, 'output': {0: 'batch'}})
```

## 📝 Requirements

```
torch==2.5.1
torchvision==0.20.1
numpy==2.1.3
scipy==1.14.1
scikit-learn==1.5.2
matplotlib==3.9.2
seaborn==0.13.2
tqdm==4.66.5
pyyaml==6.0.1
```

## 🧪 Testing

Run the test suite before training:

```bash
python test_pipeline.py
```

Tests cover:
- ✅ All imports
- ✅ Model creation & forward pass
- ✅ Dataset & DataLoaders
- ✅ Preprocessing pipeline
- ✅ Visualization functions

## 📚 References

- [CWRU Bearing Data Center](https://engineering.case.edu/bearingdatacenter/)
- [1D CNN for Fault Diagnosis](https://arxiv.org/abs/1609.03312)
- [PyTorch Documentation](https://pytorch.org/docs/stable/index.html)

## 📄 License

MIT License - Feel free to use and modify for your projects.