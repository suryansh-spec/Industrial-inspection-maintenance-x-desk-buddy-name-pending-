# Research Paper Outline: DeskBuddy Industrial Inspection ML Pipeline

**Target Venue:** IEEE Sensors Journal / IEEE Transactions on Instrumentation and Measurement / MDPI Sensors
**Target Length:** 6–8 pages (conference) or 12–15 pages (journal)

---

## 1. Title

**"Deep Residual 1D-CNN with Physics-Informed RUL for Bearing Fault Diagnosis in Edge-Deployed Industrial Inspection Systems"**

Alternative: **"ExtensiveCNN: A Residual CNN with Spectral Branch for CWRU Bearing Fault Classification and Prognostics"**

---

## 2. Abstract (200–250 words)

Bearing faults are a leading cause of rotating machinery failure. Early and accurate fault diagnosis combined with remaining useful life (RUL) prediction enables predictive maintenance and reduces unplanned downtime. This paper presents the industrial inspection module of DeskBuddy, an ESP32-S3-based desk companion system, featuring a strengthened machine learning pipeline for CWRU bearing fault classification and RUL prediction.

We replace the original shallow 3-layer CNN with ExtensiveCNN, a deep residual 1D-CNN architecture incorporating squeeze-and-excitation attention, dilated convolutions, and an optional spectral (FFT) branch. The model is available in extensive (~9.9M parameters, server) and light (~1.1M parameters, edge) variants. Training employs cosine annealing with warm restarts, label smoothing, mixup augmentation, class-balanced weighted sampling, exponential moving average weights, and mixed-precision AMP on NVIDIA GPU.

For prognostics, we introduce a physics-informed RUL engine combining exponential degradation, linear trend, and Paris' law crack-growth models, with ISO 10816-3 severity classification and uncertainty quantification.

On the CWRU 4-class benchmark (Normal, Inner Race, Ball, Outer Race at 12k drive-end), ExtensiveCNN achieves 100% test accuracy with perfect per-class metrics. Seventeen research-grade visualizations support the analysis. We discuss data-leakage limitations and outline paths to deployment on held-out recordings and real-world sensor data.

**Keywords:** bearing fault diagnosis, 1D-CNN, CWRU dataset, remaining useful life, prognostics, ISO 10816-3, Paris' law, edge AI

---

## 3. Introduction (1–1.5 pages)

### 3.1 Motivation
- Rotating machinery is critical in industrial applications
- Bearing faults lead to catastrophic failure if undetected
- Predictive maintenance reduces downtime and maintenance costs
- Edge deployment enables local, real-time diagnosis without cloud dependency

### 3.2 Problem Statement
- Classify bearing vibration into fault categories (normal, inner race, ball, outer race)
- Predict remaining useful life for maintenance scheduling
- Deploy on resource-constrained hardware (ESP32-S3 + backend PC)

### 3.3 Contributions
1. ExtensiveCNN: deep residual 1D-CNN with SE attention and optional spectral branch
2. Physics-informed RUL engine (exponential + linear + Paris' law) with uncertainty quantification
3. Extended CWRU data pipeline (64 MAT files, augmentation, overlapping windows)
4. GPU-accelerated training and inference (CUDA 12.4, RTX 3060)
5. Integration into a complete desk companion + industrial inspection system

### 3.4 Paper Organization
- Section 2: Related Work
- Section 3: Methodology (data, model, training, RUL)
- Section 4: Experimental Setup
- Section 5: Results
- Section 6: Discussion & Limitations
- Section 7: Conclusion & Future Work

---

## 4. Related Work (1 page)

### 4.1 Bearing Fault Diagnosis
- Traditional methods: RMS, kurtosis, crest factor, envelope analysis
- Machine learning: SVM, Random Forest, k-NN on handcrafted features
- Deep learning: 1D-CNN, 2D-CNN on spectrograms, LSTM, ResNet

### 4.2 Remaining Useful Life Prediction
- Model-based: Paris' law, Archard's wear model
- Data-driven: LSTM, RNN, CNN-RNN hybrids
- Hybrid: physics-informed neural networks

### 4.3 Gap
- Few systems combine classification + RUL in a single edge-deployed pipeline
- Limited use of physics-informed degradation models with uncertainty quantification
- Most research uses held-out recordings; few address data leakage from window-level splits

---

## 5. Methodology (2–2.5 pages)

### 5.1 Dataset (CWRU)
- Source: Case Western Reserve University Bearing Data Center
- Drive-end acceleration at 12 kHz
- Fault types: normal, inner race, ball, outer race
- Fault diameters: 0.007", 0.014", 0.021"
- Load conditions: 0–3 hp (1797, 1772, 1750, 1730 RPM)

### 5.2 Preprocessing
- Fixed-length windows (1024 samples, ~85 ms)
- 50% overlap with random jitter
- Data augmentation: jitter (±2%), amplitude scaling (0.9–1.1×), circular shift
- Stratified train/val/test split (70/15/15)

### 5.3 Model Architecture (ExtensiveCNN)
- 6-stage residual architecture with squeeze-and-excitation
- Dilated convolutions (dilation up to 4×)
- Global average pooling + classifier head with dropout
- Optional spectral branch (FFT magnitude)
- Extensive (~9.9M) vs Light (~1.1M) variants

### 5.4 Training Strategy
- AdamW optimizer (lr=1e-3, wd=1e-4)
- CosineAnnealingWarmRestarts scheduler
- LabelSmoothingCrossEntropy (ε=0.1) + inverse class frequency weights
- Mixup augmentation (α=0.2)
- EMA weights (decay=0.999)
- AMP mixed precision on CUDA
- Early stopping (patience=15)

### 5.5 RUL / Prognostics Engine
- ISO 10816-3 severity zones (A–D)
- Multi-model degradation: exponential, linear, Paris' law
- Conservative RUL = min of all models
- Uncertainty from trend residuals
- Blended health index (ISO health − degradation penalty)

---

## 6. Experimental Setup (0.5 pages)

| Setting | Value |
|---------|-------|
| Dataset | CWRU minimal 4-class |
| Sampling rate | 12 kHz |
| Window size | 1,024 samples |
| Split | 70/15/15 stratified |
| Model | ExtensiveCNN-light |
| Epochs | 100 (early stopped at 53) |
| Hardware | NVIDIA RTX 3060 (CUDA 12.4) |

---

## 7. Results (1.5–2 pages)

### 7.1 Classification Performance
- Test accuracy: 100%
- Per-class: precision=recall=F1=1.000 for all 4 classes
- Confusion matrix: perfect diagonal

### 7.2 Visualizations
- 17 figures covering time domain, frequency domain, time-frequency, training dynamics, classification diagnostics
- Key finding: RMS and kurtosis clearly separate fault classes (Outer Race: RMS=0.67, Kurtosis=7.69; Normal: RMS=0.07, Kurtosis=2.76)

### 7.3 RUL Results
- motor_1 (Normal): 82.5% health, 245 days RUL, low urgency
- motor_2 (Inner Race): dynamic RUL based on trend physics
- Uncertainty intervals and projected failure dates

### 7.4 Ablation Studies (Suggested)
- With/without spectral branch
- With/without mixup
- With/without EMA
- Light vs Extensive variant

---

## 8. Discussion & Limitations (1 page)

### 8.1 Data Leakage
- Window-level split allows same-recording windows in train/test
- 100% accuracy is optimistic
- Solution: held-out recording-level evaluation

### 8.2 Small Dataset
- Only 4 recordings in minimal preset
- Comprehensive preset (64 files, 23 classes) available but not yet evaluated

### 8.3 Single-Axis Limitation
- Drive-end acceleration only
- Multi-axis (x/y/z) may improve fault separability

### 8.4 Real-World Deployment
- ESP32-S3 ADXL345 may have different noise characteristics than CWRU accelerometers
- Domain adaptation may be needed

---

## 9. Conclusion & Future Work (0.5–1 page)

### 9.1 Summary
- ExtensiveCNN achieves 100% accuracy on CWRU 4-class benchmark
- Physics-informed RUL engine with uncertainty quantification
- Complete pipeline integrated into DeskBuddy desk companion system

### 9.2 Future Work
- Evaluate on held-out CWRU recordings (different file IDs)
- Comprehensive 23-class evaluation
- Multi-axis (x/y/z) input
- Domain adaptation to real ESP32-S3 ADXL345 data
- Wake word detection and streaming voice for the desk companion
- OTA firmware updates for deployed units

---

## 10. References (Suggested)

1. Case Western Reserve University Bearing Data Center. https://engineering.case.edu/bearingdatacenter
2. ISO 10816-3:2009. Mechanical vibration — Evaluation of machine vibration — Part 3.
3. Paris, P., Erdogan, F. (1963). A critical analysis of crack propagation laws.
4. Zhao, et al. (2019). Bearing fault diagnosis using 1D-CNN. IEEE Sensors Journal.
5. He, et al. (2016). Deep residual learning for image recognition. CVPR.
6. Hu, et al. (2018). Squeeze-and-excitation networks. CVPR.
7. Zhang, et al. (2017). mixup: Beyond empirical risk minimization. ICLR.

---

## Figures to Include (from artifacts/)

| Figure | File | Caption |
|--------|------|---------|
| Fig 1 | `02_time_domain_waveforms.png` | Time-domain waveforms for each fault class |
| Fig 2 | `03_fft_spectra.png` | FFT spectra showing frequency content differences |
| Fig 3 | `05_spectrograms.png` | Time-frequency spectrograms |
| Fig 4 | `06_feature_boxplots.png` | Statistical feature distributions (RMS, kurtosis, crest) |
| Fig 5 | `09_rms_vs_kurtosis.png` | RMS vs. kurtosis scatter showing class separability |
| Fig 6 | `10_training_curves.png` | Training and validation loss/accuracy |
| Fig 7 | `12_confusion_matrix.png` | Test confusion matrix |
| Fig 8 | `15_roc_curves.png` | One-vs-rest ROC curves |

---

## Tables to Include

| Table | Content |
|-------|---------|
| Table 1 | Experimental setup (hyperparameters, hardware) |
| Table 2 | Classification results (per-class precision/recall/F1/support) |
| Table 3 | Confusion matrix |
| Table 4 | RUL results for mock fleet |
| Table 5 | Model parameter count (extensive vs light) |

---

## Where to Place This

Save as: `ml/bearing_fault_desk_buddy_updated/RESEARCH_PAPER_OUTLINE.md`

This outline provides a complete structure for converting the ML work into a research paper. All 17 visualizations, the trained model, and experimental data are already generated and available in the `artifacts/` and `trained_models/` directories.
