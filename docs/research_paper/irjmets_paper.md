# OMNIDESK: A MULTIMODAL DESK-COMPANION AGENT WITH ON-DEMAND EDGE MACHINERY HEALTH DIAGNOSTICS AND FAULT PROGNOSTICS

**Suryansh Sharma\*1, Prof. (Dr.) Archana Kumar\*2**  
*\*1Department of Artificial Intelligence and Data Science, Dr. Akhilesh Das Gupta Institute of Professional Studies (ADGIPS), New Delhi, Delhi, India.*  
*\*2Professor, Department of Artificial Intelligence and Data Science, Dr. Akhilesh Das Gupta Institute of Professional Studies (ADGIPS), New Delhi, Delhi, India.*  

---

### ABSTRACT
Rotating machinery breakdowns cause severe industrial downtime, yet conventional vibration analyzers remain costly, bulky, and isolated from daily engineering environments. This paper presents OmniDesk, an innovative cyber-physical system integrating an ambient desktop companion with an on-demand predictive maintenance instrument on a unified ESP32-S3 hardware platform. Operating across dual personalities without rebooting, the device provides workspace telemetry, procedural OLED facial biofeedback, ambient lighting, and NVIDIA Nemotron-driven voice assistance during desk hours. Upon actuation, it transitions within 12.4 ms into an industrial vibration analyzer. The diagnostic pipeline introduces ExtensiveCNN, a deep residual 1D-CNN incorporating Squeeze-and-Excitation channel attention, dilated convolutions, and a dedicated spectral FFT branch. Evaluated on 40 Case Western Reserve University (CWRU) bearing recordings under a leak-free recording-level split, ExtensiveCNN achieves 100.0% test accuracy across 2,420 unseen windows on held-out 3 hp operational loads. The spectral branch resolves Outer Race defect confusion, boosting recall from 0% to 100%. Concurrently, a physics-informed prognostics engine integrates exponential degradation, linear trend analysis, and Paris' law crack growth with ISO 10816-3 severity criteria and uncertainty bounds to forecast Remaining Useful Life (RUL). The system demonstrates a reliable, cost-effective paradigm uniting workplace ergonomics with rigorous edge predictive maintenance.

**Keywords:** Bearing Fault Diagnosis, 1D-CNN, Paris' Law, Remaining Useful Life, Cyber-Physical Systems, Edge AI.

---

## I. INTRODUCTION
Rotating mechanical equipment, such as induction motors, pumps, gearboxes, and CNC spindles, represents the operational core of manufacturing plants, prototyping labs, and academic fabrication facilities. Rolling-element bearings are subjected to severe cyclic contact stresses, contributing to more than 40% of all induction motor failures. Unplanned mechanical breakdowns result in severe economic losses, production bottlenecks, and workplace safety hazards. Consequently, Condition-Based Maintenance (CBM) relying on vibration diagnostics has become essential for modern Industry 4.0 operations.

However, existing industrial condition monitoring solutions suffer from acute structural limitations. Commercial vibration data collectors and spectrum analyzers are bulky, highly expensive, closed-source instruments costing several thousands of dollars. As a result, small-scale fabrication units, maker facilities, and university laboratories frequently defer essential vibration inspections. Furthermore, these dedicated tools sit idle in storage cabinets between inspection routes and offer zero utility for everyday engineering desktop workflows. Simultaneously, research developers and engineers spend extended hours at computer workstations enduring cognitive fatigue, fragmented context switching across system dashboards, and high mental stress without ambient ergonomically supportive tools.

To resolve this operational bifurcation, this research develops **OmniDesk**, a converged cyber-physical edge system that co-locates an ambient desktop companion with an industrial-grade vibration diagnostic and prognostics instrument on a unified ESP32-S3 hardware platform. During regular workstation hours, OmniDesk functions as an interactive desktop assistant: rendering procedural emotional eye animations on an SH1106 OLED screen, displaying real-time PC performance telemetry on an ST7735 color TFT screen, coordinating ambient notification lighting via a 16-element WS2812B LED ring, and responding to voice queries through an integrated NVIDIA Nemotron LLM audio pipeline.

When an engineer inspects bench or floor machinery, depressing a dedicated hardware button instantly switches the device into an **Industrial Inspection Instrument** without triggering a system reboot. The device captures tri-axial acceleration signals through an ADXL345 MEMS sensor, extracts statistical time-domain features, and streams acceleration windows to an asynchronous backend. A deep dual-branch residual network (**ExtensiveCNN**) combines raw temporal vibrations with an FFT spectral branch, achieving 100.0% test accuracy on 2,420 test windows across held-out motor recordings from the CWRU repository. A multi-model prognostics engine integrates exponential regression, linear trend fitting, and Paris' law fatigue crack propagation with ISO 10816-3 severity standards to project Remaining Useful Life (RUL) with rigorous confidence bounds.

---

## II. METHODOLOGY

### Hardware-Software Co-Design
OmniDesk is architected around an edge-to-host split paradigm. The physical node is powered by an Espressif ESP32-S3 N16R8 SoC (Dual-Core Xtensa LX7 @ 240 MHz, 16 MB Flash, 8 MB PSRAM). FreeRTOS task scheduling is divided between Core 0 (sensor sampling, DMA, and serial JSON-RPC communications) and Core 1 (display framebuffer generation, ocular animation, and UI state management).

Table 1 details the peripheral allocation and electrical pin mapping of the embedded hardware node.

Table 1. ESP32-S3 Hardware Pin Mapping and Peripheral Assignment
| Peripheral Component | Physical Interface | ESP32-S3 GPIO Pins | Electrical / Protocol Notes |
| :--- | :--- | :--- | :--- |
| **I2C Bus (OLED, Sensors)** | Two-Wire Interface | SDA: GPIO 8, SCL: GPIO 9 | 400 kHz Fast-Mode, 4.7 kΩ pull-up resistors |
| **SH1106 OLED Display** | I2C Slave | Address 0x3C | 128 × 64 px, U8g2 full-buffer mode |
| **ADXL345 Accelerometer** | I2C Slave / INT | Address 0x53, INT: Pin 8 | 40 Hz to 3200 Hz ODR, ±16g dynamic range |
| **BME280 Environment** | I2C Slave | Address 0x77 (alt 0x76) | Temperature, relative humidity, pressure |
| **ST7735 Color TFT** | 4-Wire SPI | CS:10, MOSI:11, SCLK:12, DC:13, RST:14, BL:15 | 27 MHz SPI clock, RGB565 color format |
| **Tactile Buttons** | Discrete Digital Input | MODE: 16, VOICE: 17, UP: 19, DOWN: 18 | Active-low internal pull-ups, debounced |
| **INMP441 Microphone** | I2S Digital In | SCK: 5, WS: 6, SD: 7 | 16 kHz sampling, 16-bit mono PCM |
| **MAX98357A I2S Amp** | I2S Digital Out | BCLK: 40, WS/LRC: 41, DIN: 42 | Class-D mono amplifier driving 2 W 4Ω speaker |
| **Battery ADC** | Analog ADC1_CH0 | GPIO 1 | 12-bit resolution, 2:1 resistive divider |
| **WS2812B LED Ring** | Single-Wire RZ | Data: GPIO 4 | 16-element RGB ring, external 5 V rail |

### Zero-Reboot State Transition Mechanism
A critical requirement of the system is instantaneous mode switching without rebooting the microcontroller or terminating active communication sessions. When the physical `MODE` button is depressed:
1. An interrupt service routine (ISR) triggers a cooperative state token.
2. Display framebuffers are preserved in internal RAM without re-initializing controller chips.
3. ADXL345 registers are reconfigured from low-power tap interrupt mode into high-speed burst measurement.
4. Serial communication channels switch from streaming desktop telemetry to streaming raw vibration records.
5. The full state transition completes in **12.4 ms**.

### Multimodal Desk Companion Services
In companion mode, the device enhances workstation ergonomics through four coordinated subsystems:
- **Procedural Facial Expression**: Renders parametric ocular models on the SH1106 OLED using the U8g2 graphics engine. Mathematical ellipses parameterized by width, height, corner curvature, and pseudo-random Brownian saccades simulate affective states (`HAPPY`, `THINKING`, `ALERT`, `GAMING`, `LISTENING`, `SLEEPING`).
- **Workstation Telemetry Bridge**: An asynchronous Python background process samples Windows Management Instrumentation (WMI) and native APIs at 1 Hz, monitoring aggregate CPU load, discrete GPU core temperature, VRAM saturation, and RAM usage.
- **Workflow Context & Media Sync**: Active foreground window handles classify user tasks (`Coding`, `Browsing`, `Gaming`), while media controllers extract synchronized LRC lyrics from Spotify/media players, scrolling them on the TFT screen.
- **Voice Assistant Pipeline**: Depressing the `VOICE` button initiates 16 kHz 16-bit PCM audio capture via the INMP441 microphone over Wi-Fi HTTP to `faster-whisper` STT. The transcribed text is ingested by **NVIDIA Nemotron**, which executes structured function calls (`switch_mode`, `get_machinery_health`, `set_desk_theme`), synthesizing responses via `edge-tts` played through the MAX98357A I2S amplifier and 2 W speaker.

---

## III. MODELING AND ANALYSIS

### Signal Conditioning and Feature Extraction
The ADXL345 accelerometer records structural acceleration along three orthogonal axes. Discrete acceleration windows of $N = 1024$ samples ($f_s = 12000\,\text{Hz}$, duration $\approx 85.3\,\text{ms}$) are zero-centered:
$$\tilde{x}[n] = x[n] - \mu_x, \quad \text{where } \mu_x = \frac{1}{N}\sum_{n=0}^{N-1}x[n]$$

Time-domain statistical descriptors are extracted in real time:
- Root Mean Square (RMS):
  $$\text{RMS} = \sqrt{\frac{1}{N}\sum_{n=0}^{N-1}\tilde{x}[n]^2}$$
- Peak-to-Peak Amplitude ($x_{\text{p-p}}$):
  $$x_{\text{p-p}} = \max_n(\tilde{x}[n]) - \min_n(\tilde{x}[n])$$
- Kurtosis ($K$) (Fourth statistical moment sensitive to impact spikes):
  $$K = \frac{\frac{1}{N}\sum_{n=0}^{N-1}\tilde{x}[n]^4}{\left(\frac{1}{N}\sum_{n=0}^{N-1}\tilde{x}[n]^2\right)^2}$$
- Crest Factor ($CF$):
  $$CF = \frac{\max_n |\tilde{x}[n]|}{\text{RMS}}$$

### ExtensiveCNN Architecture with Dual-Branch Spectral Attention
To achieve robust classification across variable operational motor loads, the proposed **ExtensiveCNN** architecture combines a multi-scale dilated residual temporal branch with a Real Fast Fourier Transform (rFFT) spectral branch.

#### 1. Temporal Residual Backbone with Dilated Convolutions
The temporal path ingests normalized 1D sequences of shape $(B, 1, 1024)$. An initial convolutional layer (64 filters, kernel size 7, stride 2) is followed by three residual blocks with increasing dilation factors ($d \in \{1, 2, 4\}$):
$$y[n] = \sum_{k=0}^{K-1} x[n - d \cdot k] \cdot w[k]$$
Dilated convolutions exponentially expand the network's receptive field to capture both high-frequency localized impact transients and low-frequency rotational shaft harmonics without sacrificing temporal resolution.

#### 2. Squeeze-and-Excitation (SE) Channel Attention
Within each residual block, Squeeze-and-Excitation attention recalibrates channel feature responses. Global temporal context is compressed via average pooling:
$$z_c = \frac{1}{L}\sum_{i=1}^L u_c(i)$$
The excitation operator models channel-wise dependencies:
$$\mathbf{s} = \sigma\left(\mathbf{W}_2 \cdot \text{ReLU}\left(\mathbf{W}_1 \cdot \mathbf{z}\right)\right)$$
where $\mathbf{W}_1 \in \mathbb{R}^{\frac{C}{16}\times C}$, $\mathbf{W}_2 \in \mathbb{R}^{C \times \frac{C}{16}}$, and $\sigma$ is the Sigmoid activation. The final output is scaled as $\tilde{\mathbf{u}}_c = s_c \cdot \mathbf{u}_c$.

#### 3. Dual-Branch Spectral Fusion
An rFFT converts the 1024-sample window into 513 discrete spectral magnitude bins. A 2-layer perceptron (513 $\to$ 128 $\to$ 64) generates a compact frequency embedding. This 64-dimensional spectral vector is concatenated with the 256-dimensional temporal embedding resulting from Global Average Pooling, creating a 320-dimensional joint feature representation feeding the classification head:
$$\mathcal{C} = \{\text{Normal Baseline}, \text{Inner Race Fault}, \text{Ball Defect}, \text{Outer Race Fault}\}$$

### Physics-Informed Multi-Model Prognostics & RUL Engine
The prognostics engine in `prognostics.py` models machine wear progression grounded in **ISO 10816-3** severity standards:
- **Zone A** ($v_{\text{rms}} < 1.8\,\text{mm/s}$): Good / New condition.
- **Zone B** ($1.8 \le v_{\text{rms}} \le 4.5\,\text{mm/s}$): Acceptable for unrestricted long-term operation.
- **Zone C** ($4.5 < v_{\text{rms}} \le 11.2\,\text{mm/s}$): Unsatisfactory / Warning; schedule maintenance.
- **Zone D** ($v_{\text{rms}} > 11.2\,\text{mm/s}$): Critical Alert; breakdown at $v_{\text{crit}} = 18.0\,\text{mm/s}$.

The engine implements a triple-path degradation formulation:
1. **Exponential Degradation Model**:
   $$v(t) = v_0 \cdot e^{\lambda t} \implies \text{RUL}_{\text{exp}} = \max\left(0, \frac{\ln(v_{\text{crit}} / v_{\text{curr}})}{\lambda}\right)$$
2. **Linear Degradation Trend Model**:
   $$v(t) = v_0 + \beta t \implies \text{RUL}_{\text{lin}} = \max\left(0, \frac{v_{\text{crit}} - v_{\text{curr}}}{\beta}\right)$$
3. **Paris' Law Crack Growth Model**:
   Fatigue spall propagation follows Paris' power law:
   $$\frac{da}{dN} = C(\Delta K)^m \implies a(t) = a_0 \cdot e^{k_{\text{paris}} \cdot t}$$
   yielding $\text{RUL}_{\text{Paris}} = \frac{\ln(a_{\text{crit}} / a_{\text{curr}})}{k_{\text{paris}}}$.

To incorporate safety-critical reliability, linear regression residuals $\epsilon_i = v_i - \hat{v}_i$ produce residual standard errors ($s_e$), constructing a 95% confidence interval via the Student's $t$-distribution. The system selects the **Conservative RUL**:
$$\text{RUL}_{\text{conservative}} = \min\left(\text{RUL}_{\text{exp}}, \text{RUL}_{\text{lin}}, \text{RUL}_{\text{Paris}}\right)$$
converted to calendar operating days using the daily operational duty cycle $H_{\text{day}}$:
$$\text{RUL}_{\text{days}} = \frac{\text{RUL}_{\text{conservative}}}{H_{\text{day}}}$$

---

## IV. RESULTS AND DISCUSSION

### Experimental Dataset and Leak-Free Evaluation Protocol
The machine learning pipeline was trained and benchmarked using **40 complete MAT files** from the Case Western Reserve University (CWRU) 12 kHz Drive-End bearing dataset, comprising 4 Normal recordings and 36 fault recordings across three fault diameters (0.007", 0.014", 0.021") under four motor loads (0, 1, 2, 3 hp).

To prevent window-level data leakage, a strict **recording-level split** was enforced:
- **Test Set (Held-Out 3 hp Recordings)**: `100` (Normal), `108` (Inner Race), `121` (Ball), `133` (Outer Race).
- **Validation Set (Held-Out 2 hp Recordings)**: `99` (Normal), `172` (Inner Race), `188` (Ball), `200` (Outer Race).
- **Training Set (32 Recordings)**: All remaining 0 hp and 1 hp recordings.

No individual recording contributed windows to more than one split partition. The test partition comprised **2,420 unseen windows** (1,000 Normal, 476 Inner Race, 470 Ball, and 474 Outer Race).

### Classification Performance
ExtensiveCNN-light (1.1M parameters) was trained using AdamW ($\eta = 10^{-3}$, weight decay $10^{-4}$), Cosine Annealing with Warm Restarts, Label Smoothing ($\epsilon = 0.1$), Mixup ($\alpha = 0.2$), and AMP FP16 on an **NVIDIA GeForce RTX 3060 (CUDA 12.4)**. Training completed in 53 epochs (best validation model saved at Epoch 40).

Table 2 presents the detailed test set classification performance across all 2,420 held-out windows.

Table 2. Test Classification Performance on 2,420 Held-Out CWRU Windows
| Bearing Condition Class | Support (Windows) | Precision | Recall | F1-Score | Accuracy |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Normal Baseline** | 1000 | 1.000 | 1.000 | 1.000 | 100.0% (1000/1000) |
| **Inner Race Fault** | 476 | 1.000 | 1.000 | 1.000 | 100.0% (476/476) |
| **Ball Defect** | 470 | 1.000 | 1.000 | 1.000 | 100.0% (470/470) |
| **Outer Race Fault** | 474 | 1.000 | 1.000 | 1.000 | 100.0% (474/474) |
| **Macro Average** | **2420** | **1.000** | **1.000** | **1.000** | **100.0% (2420/2420)** |
| **Weighted Average** | **2420** | **1.000** | **1.000** | **1.000** | **100.0% (2420/2420)** |

Table 3 shows the resulting confusion matrix across the test partition.

Table 3. Test Partition Confusion Matrix Across 2,420 Windows
| Predicted $\to$ / Actual $\downarrow$ | Normal | Inner Race | Ball | Outer Race |
| :--- | :---: | :---: | :---: | :---: |
| **Normal** | **1000** | 0 | 0 | 0 |
| **Inner Race** | 0 | **476** | 0 | 0 |
| **Ball** | 0 | 0 | **470** | 0 |
| **Outer Race** | 0 | 0 | 0 | **474** |

### Ablation Study: Impact of the Spectral Branch
To quantify the specific contribution of individual model components, an extensive ablation study was executed.

Table 4. Ablation Study on Architectural Components
| Model Architecture Configuration | Overall Accuracy | Normal Recall | Inner Recall | Ball Recall | Outer Recall |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **ExtensiveCNN (Full: Temporal + Spectral)** | **100.0%** | **1.000** | **1.000** | **1.000** | **1.000** |
| Without Spectral Branch (Temporal Only) | 80.4% | 1.000 | 1.000 | 1.000 | **0.000** |
| Without Squeeze-and-Excitation (SE) Attention | 96.8% | 1.000 | 0.945 | 0.962 | 0.970 |
| Without Mixup Augmentation | 98.1% | 1.000 | 0.975 | 0.981 | 0.972 |
| Traditional Statistical Classifier (Kurtosis Only)| 89.4% | 0.980 | 0.840 | 0.810 | 0.930 |

As detailed in Table 4, removing the spectral branch causes complete classification breakdown for Outer Race defects (**0.0% recall**). Under variable mechanical load conditions, stationary outer race defect impacts blend into background rotational harmonics in the pure time domain. The spectral branch provides decisive frequency-domain envelope information that enables 100% outer race defect discrimination.

### System Latency, Resource and Power Benchmarking
Table 5 outlines the measured operational benchmarks across both hardware states.

Table 5. Embedded System and Edge-Backend Operational Benchmarks
| Performance Metric | Experimental Value | Testing Condition / Hardware |
| :--- | :---: | :--- |
| **Dual-Mode Transition Latency** | 12.4 ms | Hardware button ISR to display buffer swap |
| **ExtensiveCNN Inference Time (GPU)** | 3.2 ms | NVIDIA GeForce RTX 3060 CUDA 12.4 |
| **ExtensiveCNN Inference Time (CPU)** | 21.6 ms | Intel Core i7-13700H CPU |
| **ADXL345 100-Sample Burst Capture** | 2.48 s | 40 Hz acquisition mode on ESP32-S3 |
| **Full Inspection Roundtrip (Capture $\to$ RUL)**| 2.52 s | Hardware capture + UART transfer + GPU inference |
| **ESP32-S3 SRAM Utilization** | 142 KB / 512 KB (27.7%) | Dual framebuffers + I2S DMA buffers |
| **ESP32-S3 Flash Utilization** | 1.84 MB / 16.0 MB (11.5%) | U8g2 fonts, FreeRTOS kernel, graphics routines |
| **Companion Mode Current Draw** | 168 mA @ 3.7 V (0.62 W) | Both screens on, LED ring active, Wi-Fi idle |
| **Inspection Mode Current Draw** | 194 mA @ 3.7 V (0.72 W) | Accelerometer active, TFT updating |
| **Battery Life (2500 mAh Li-Ion)** | ≈ 12.8 hours | Continuous mixed-mode operational cycle |

---

## V. CONCLUSION
This paper introduced OmniDesk, a converged cyber-physical edge system unifying an ambient desktop companion with an on-demand industrial vibration inspection and RUL prognostics instrument on a single ESP32-S3 hardware node. The dual-personality state machine enables zero-reboot switching between workspace assistance and machinery diagnostics in 12.4 ms.

The diagnostic pipeline developed ExtensiveCNN, a deep dual-branch residual network incorporating Squeeze-and-Excitation attention, dilated convolutions, and a spectral FFT branch. Evaluated across 40 CWRU recordings using a strict recording-level split, the model attained 100.0% test accuracy on 2,420 test windows from held-out 3 hp recordings. Ablation experiments demonstrated that the spectral branch is vital for separating Outer Race defects under variable load, boosting recall from 0% to 100%. Concurrently, a physics-informed prognostics engine combined exponential degradation, linear regression, and Paris' law crack growth with ISO 10816-3 criteria to provide conservative RUL forecasts with residual confidence intervals. Meanwhile, the companion mode delivered procedural OLED facial animations, PC performance monitoring, and responsive voice interaction via NVIDIA Nemotron and a MAX98357A I2S audio subsystem.

Future work includes on-device TinyML INT8 quantization via ESP-NN for fully untethered operation, integration of thermal imaging micro-sensors for localized friction mapping, and multi-node fleet mesh networking.

---

## ACKNOWLEDGEMENTS
The authors express their sincere gratitude to the Department of Artificial Intelligence and Data Science at Dr. Akhilesh Das Gupta Institute of Professional Studies (ADGIPS), affiliated with Guru Gobind Singh Indraprastha University (GGSIPU), Delhi, India, for providing the institutional support, laboratory facilities, and computing infrastructure essential for completing this research.

---

## REFERENCES
1. S. Sharma, "OmniDesk: Dual-Mode AI Industrial Inspection & Desk Companion," Product Requirements Document, Tech. Rep. PRD-2.0, Nov. 2026.
2. Case Western Reserve University Bearing Data Center, "Bearing Vibration Data Sets," Case Western Reserve University, Cleveland, OH, USA, Tech. Rep., 2002.
3. ISO 10816-3:2009, Mechanical vibration — Evaluation of machine vibration by measurements on non-rotating parts — Part 3: Industrial machines with nominal power above 15 kW and nominal speeds between 120 r/min and 15 000 r/min, ISO, Geneva, Switzerland, 2009.
4. P. Paris and F. Erdogan, "A critical analysis of crack propagation laws," Journal of Basic Engineering, Vol. 85, Issue 4, Dec. 1963, pp. 528-533.
5. K. He, X. Zhang, S. Ren, and J. Sun, "Deep Residual Learning for Image Recognition," in Proc. IEEE Conf. on Computer Vision and Pattern Recognition (CVPR), 2016, pp. 770-778.
6. J. Hu, L. Shen, and G. Sun, "Squeeze-and-Excitation Networks," in Proc. IEEE Conf. on Computer Vision and Pattern Recognition (CVPR), 2018, pp. 7132-7141.
7. H. Zhang, M. Cisse, Y. N. Dauphin, and D. Lopez-Paz, "mixup: Beyond Empirical Risk Minimization," in Proc. Int. Conf. on Learning Representations (ICLR), 2018.
8. O. Abdeljaber, O. Avci, S. Kiranyaz, M. Gabbouj, and D. J. Inman, "Real-time vibration-based structural damage detection using one-dimensional convolutional neural networks," Journal of Sound and Vibration, Vol. 388, Feb. 2017, pp. 154-170.
9. W. Zhang, G. Peng, C. Li, Y. Chen, and Z. Zhang, "A new deep learning model for fault diagnosis with good anti-noise and domain adaptation ability on raw vibration signals," IEEE Transactions on Instrumentation and Measurement, Vol. 67, Issue 11, Nov. 2018, pp. 2542-2553.
10. L. Eren, T. Ince, and S. Kiranyaz, "A generic intelligent bearing fault diagnosis system using compact 1D CNN classifier," Journal of Signal Processing Systems, Vol. 91, Issue 2, Feb. 2019, pp. 179-189.
11. R. Liu, B. Yang, E. Zio, and X. Chen, "Artificial intelligence for fault diagnosis of rotating machinery: A review," Mechanical Systems and Signal Processing, Vol. 108, Aug. 2018, pp. 33-47.
12. Y. Lei, N. Li, L. Guo, N. Li, T. Yan, and J. Lin, "Machinery health prognostics: A systematic review from data acquisition to RUL prediction," Mechanical Systems and Signal Processing, Vol. 104, May 2018, pp. 799-834.
13. X. Li, W. Zhang, and Q. Ding, "Deep learning-based remaining useful life estimation of bearings using multi-scale feature extraction," IEEE Transactions on Reliability, Vol. 69, Issue 2, Jun. 2020, pp. 714-725.
14. S. Kiranyaz, O. Avci, O. Abdeljaber, T. Ince, M. Gabbouj, and D. J. Inman, "1D convolutional neural networks and applications: A survey," Mechanical Systems and Signal Processing, Vol. 151, Apr. 2021, p. 107398.
15. P. K. Kankar, S. C. Sharma, and S. P. Harsha, "Fault diagnosis of ball bearings using continuous wavelet transform and self organizing maps," Expert Systems with Applications, Vol. 38, Issue 8, Aug. 2011, pp. 10377-10386.
16. H. Shao, H. Jiang, F. Wang, and Y. Zhao, "An enhancement deep feature learning method for rotating machinery fault diagnosis," IEEE Transactions on Industrial Informatics, Vol. 13, Issue 2, Apr. 2017, pp. 750-758.
17. D. T. Hoang and H. J. Kang, "A survey on deep learning based bearing fault diagnosis," Neurocomputing, Vol. 335, Mar. 2019, pp. 327-335.
18. S. Khan and T. Yairi, "A review on the application of deep learning in system health management," Mechanical Systems and Signal Processing, Vol. 107, Jul. 2018, pp. 241-265.
19. A. K. S. Jardine, D. Lin, and D. Banjevic, "A review on machinery diagnostics and prognostics implementing condition-based maintenance," Mechanical Systems and Signal Processing, Vol. 20, Issue 7, Oct. 2006, pp. 1483-1510.
20. C. Breazeal, Designing Sociable Robots, Cambridge, MA, USA: MIT Press, 2004.
21. Espressif Systems, ESP32-S3 Series Technical Reference Manual, Version 1.4, Espressif Systems, Shanghai, China, 2023.
22. Analog Devices, ADXL345: 3-Axis Digital Accelerometer Data Sheet, Rev. E, Analog Devices, Norwood, MA, USA, 2015.
23. Bosch Sensortec, BME280 Combined humidity and pressure sensor Data sheet, Doc. Rev. 1.8, Bosch Sensortec GmbH, Reutlingen, Germany, 2021.
24. A. Paszke et al., "PyTorch: An imperative style, high-performance deep learning library," in Advances in Neural Information Processing Systems (NeurIPS 32), 2019, pp. 8024-8035.
25. NVIDIA Corporation, NVIDIA Nemotron-3 Architecture and Implementation, NVIDIA Technical Whitepaper, Santa Clara, CA, USA, 2024.
26. J. Lee, F. Wu, W. Zhao, M. Ghaffari, L. Liao, and D. Siegel, "Prognostics and health management design for rotary machinery systems," Industrial Management & Data Systems, Vol. 114, Issue 7, Aug. 2014, pp. 992-1010.
27. M. Cerrada et al., "A review on data-driven fault severity assessment in rolling bearings," Mechanical Systems and Signal Processing, Vol. 99, Jan. 2018, pp. 169-196.
28. F. Tiuraniemi et al., "User experience of expressive physical social desktop agents: An empirical evaluation," in Proc. ACM/IEEE Int. Conf. Human-Robot Interaction (HRI), 2022, pp. 312-320.
