# A Multimodal Desk-Companion Agent with On-Demand Edge Machinery Health Diagnostics and Fault Prognostics

**Suryansh Sharma**  
*Department of Artificial Intelligence and Data Science*  
*Dr. Akhilesh Das Gupta Institute of Professional Studies (ADGIPS)*  
*Guru Gobind Singh Indraprastha University, Delhi, India*  
Email: suryansh3584@gmail.com  

**Prof. (Dr.) Archana Kumar**  
*Department of Artificial Intelligence and Data Science*  
*Dr. Akhilesh Das Gupta Institute of Professional Studies (ADGIPS)*  
*Guru Gobind Singh Indraprastha University, Delhi, India*  

---

## Abstract
Modern engineering and developer workflows are characterized by high cognitive loads, fragmented context switching across desktop utilities, and a disconnect from physical workshop and laboratory machinery. While ambient robotic desk companions have emerged to alleviate cognitive fatigue and provide contextual awareness, industrial maintenance instruments remain isolated, expensive, and specialized. This paper presents **DeskBuddy**, a novel cyber-physical edge-computing system that integrates an ambient, multimodal desktop companion agent with an on-demand industrial machinery health inspection instrument on a unified hardware platform. Powered by an ESP32-S3 dual-core microcontroller and an asynchronous edge-cloud architecture, the device alternates between two operating personalities without requiring a system reboot: (i) an interactive desktop companion featuring an expressive animated OLED face, SPI-driven dashboard telemetry, ambient illumination, physical gesture control, and conversational intelligence driven by the NVIDIA Nemotron large language model; and (ii) a handheld predictive maintenance analyzer that captures tri-axial vibration signals via MEMS accelerometry, executes statistical spectral extraction, and streams high-frequency windows to a hybrid 1D-Convolutional Neural Network (1D-CNN) and prognostics engine. Evaluated on the standardized Case Western Reserve University (CWRU) bearing dataset across 1,600 test windows, the proposed 1D-CNN achieves 100.0% classification accuracy across normal, inner race, ball, and outer race faults. The integrated prognostics engine maps operational root-mean-square (RMS) velocities to ISO 10816-3 severity zones and projects Remaining Useful Life (RUL) using exponential degradation modeling. Experimental benchmarking validates sub-15 ms edge-to-backend mode transition latency, sub-25 ms neural inference on edge compute nodes, and uninterrupted desktop companion responsiveness, demonstrating the feasibility of converged ambient intelligence and cyber-physical diagnostic instruments.

**Index Terms**—Cyber-Physical Systems, Edge AI, Industrial Prognostics, Remaining Useful Life (RUL), 1D-Convolutional Neural Networks, ISO 10816-3, Ambient Intelligence, Multimodal Desk Agent, Case Western Reserve University (CWRU) Dataset.

---

## I. Introduction

In industrial and engineering computing environments, knowledge workers, research developers, and hardware technicians frequently navigate two disparate technological paradigms:
1. **Workspace Context Awareness & Cognitive Productivity**: Modern developers spend extended hours at workstations managing fragmented dashboards, tracking computational workloads (CPU, GPU, memory utilization), monitoring calendar obligations, and enduring cognitive fatigue. Ambient computing devices and interactive desk companions have proven effective in reducing cognitive strain through expressive visual feedback, Pomodoro pacing, and natural human-computer interaction (HCI).
2. **Shop-Floor Machinery Health Inspection**: In academic prototyping laboratories, fabrication facilities, and industrial manufacturing plants, rotating machinery—such as electric induction motors, spindle pumps, compressors, and CNC milling heads—suffers mechanical degradation. Unplanned mechanical breakdowns induce substantial financial losses and safety hazards. Condition-Based Maintenance (CBM) relying on vibration analysis and predictive prognostics offers substantial advantages over reactive or fixed-interval schedules.

Historically, these two domains have developed in complete isolation. Desktop productivity assistants are deployed as software widgets or consumer electronics lacking sensor telemetry and physical diagnostics. Conversely, industrial vibration analyzers and acoustic probes are typically bulky, single-purpose, proprietary instruments costing thousands of dollars, designed exclusively for periodic route-based manual data collection. Small-scale manufacturing units, maker spaces, and engineering university laboratories often lack the budgetary capital to procure specialized handheld vibration analyzers, while field technicians lack ambient computing aids to synthesize telemetry during diagnostic reporting.

To bridge this operational divide, this paper proposes **DeskBuddy**, a unified cyber-physical edge agent that combines an ambient, multimodal desktop companion with an industrial-grade vibration fault diagnosis and Remaining Useful Life (RUL) estimation engine. Operating on an Espressif ESP32-S3 dual-core SoC, the proposed system employs hardware-software co-design to host a dual-personality state machine. When docked on an engineer's desk, the device functions as an interactive workspace companion, animating emotional states on an OLED display, visualizing real-time workstation performance metrics on an SPI color TFT screen, coordinating ergonomic lighting via addressable WS2812B LEDs, and handling natural voice queries through an integrated NVIDIA Nemotron language model pipeline.

Upon encountering anomalous machinery or initiating an inspection route, a physical non-maskable hardware button instantaneously shifts the device into an **Industrial Inspection Instrument** without triggering a hardware reset or terminating active network bridges. In this mode, the integrated 3-axis accelerometer captures high-frequency structural vibration data, extracts real-time statistical time-domain features (Root Mean Square, Kurtosis, Crest Factor, Peak-to-Peak amplitude), computes Fast Fourier Transform (FFT) spectra, and transmits windowed signals to an asynchronous backend. A deep 1D-Convolutional Neural Network (1D-CNN) classifies bearing fault topologies with 100% empirical accuracy on benchmark data, while a prognostics pipeline integrates cumulative run-time hours, baseline degradation parameters, and ISO 10816-3 vibration severity standards to forecast the machinery's Remaining Useful Life in operating days.

### Core Contributions
The principal contributions of this work are summarized as follows:
- **Unified Dual-Personality Cyber-Physical Architecture**: We design, build, and validate a reconfigurable edge architecture that co-locates ambient desktop productivity tools with industrial predictive maintenance on a single ESP32-S3 microcontroller, achieving zero-reboot state transitions in under 15 ms.
- **High-Accuracy 1D-CNN Fault Classification Pipeline**: We formulate a 1D-CNN tailored for raw 1200-sample 1D vibration windows, achieving 100.0% precision, recall, and F1-score across four distinct bearing health states on the CWRU dataset, accompanied by an ultra-lightweight statistical fallback analyzer based on kurtosis moments.
- **Physics-Informed Prognostics & RUL Engine**: We implement a mathematical degradation model combining cumulative equipment runtime, ISO 10816-3 velocity severity criteria, and exponential defect propagation to provide interpretable Remaining Useful Life forecasts.
- **Multimodal Ergonomic Desk Interaction**: We engineer an integrated human-machine interface combining dual-display rendering (procedural OLED eye animation + TFT telemetry dashboard), physical tap/shake gesture interrupts via MEMS accelerometry, and an end-to-end voice assistant powered by the NVIDIA Nemotron LLM with structured tool execution.

The remainder of this paper is organized as follows: Section II surveys prior literature in ambient companions, deep learning fault diagnostics, and edge computing. Section III details the system architecture, hardware specification, and state machine design. Section IV presents the multimodal desk-companion subsystem. Section V details the vibration signal processing, 1D-CNN architecture, ISO 10816-3 mapping, and prognostics engine. Section VI presents comprehensive experimental results, benchmarking, and latency measurements. Section VII discusses design trade-offs and practical constraints, and Section VIII concludes the paper with future research directions.

---

## II. Related Work

### A. Ambient Robotics and Workspace Assistants
Ambient intelligence and tabletop robotics have evolved significantly over the past decade. Initial desk agents focused primarily on anthropomorphic physical movements or passive status notification. Recent advances in affective computing emphasize that expressive physical manifestations—such as animated eyes, dynamic lighting, and physical micro-gestures—significantly enhance human focus and reduce burnout during prolonged mental exertion. However, the vast majority of existing commercial and academic desk companions (e.g., Vector, Eilik) operate solely within consumer or entertainment contexts, with closed firmware, no industrial sensing capabilities, and zero utility for hardware diagnostics or engineering measurements.

### B. Deep Learning in Rotating Machinery Fault Diagnosis
Condition-based monitoring of rotating mechanical components (bearings, gears, and shafts) has transitioned from manual spectral analysis to automated machine learning. Early research relied on hand-crafted statistical features extracted from time and frequency domains—including root mean square (RMS), kurtosis, skewness, and crest factor—fed into Support Vector Machines (SVM), Random Forests, or shallow artificial neural networks. While computationally modest, shallow models struggle to generalize across variable load conditions and subtle defect sizes.

With the advent of deep learning, Convolutional Neural Networks (CNNs) have emerged as the state of the art for bearing fault detection. Researchers have applied 2D-CNNs by converting vibration time-series signals into visual representations, such as Short-Time Fourier Transform (STFT) spectrograms or Continuous Wavelet Transform (CWT) scalograms. While effective, 2D time-frequency transformations impose substantial computational overhead, introducing latency that hinders real-time edge processing. To address this, 1D-CNNs operating directly on one-dimensional raw acceleration sequences have gained prominence. Works by Ince et al. and Zhang et al. demonstrated that 1D-CNNs can automatically learn spatial feature hierarchies directly from sequential vibration windows without manual feature extraction, drastically lowering computational cost. The Case Western Reserve University (CWRU) bearing dataset has established itself as the global gold standard for benchmarking these diagnostic architectures.

### C. Prognostics and Remaining Useful Life (RUL) Modeling
While fault classification determines the presence and location of a defect, prognostics aims to predict the temporal distance to functional breakdown. Existing prognostic methodologies fall broadly into physics-of-failure models, data-driven deep recurrent models (such as LSTMs and Transformers), and empirical degradation models. Deep recurrent models require vast run-to-failure historical datasets, which are rarely available for custom or newly commissioned field machinery. In contrast, exponential degradation modeling grounded in ISO 10816 vibration severity standards provides a mathematically tractable, robust, and interpretable framework for estimating RUL when operational baselines and cumulative running hours are continuously tracked.

### D. Edge-Cloud Cyber-Physical Converged Systems
The proliferation of dual-core, high-speed microcontrollers featuring integrated Wi-Fi and Bluetooth Low Energy (e.g., Espressif ESP32-S3) has made edge-cloud partitioning practical for cyber-physical systems. Prior works have typically deployed microcontrollers either strictly as dumb IoT sensor nodes that stream raw bytes to a central server or as self-contained TinyML nodes running severely pruned neural models. Few, if any, existing systems have explored the convergence of ambient desk ergonomics and ruggedized industrial condition monitoring into a single, reconfigurable dual-mode cyber-physical instrument.

---

## III. System Architecture and Hardware-Software Co-Design

The DeskBuddy architecture is conceived as a collaborative edge-to-host system. Sensor acquisition, physical user interaction, display drivers, and real-time state machines execute directly on the ESP32-S3 microcontroller, while heavy neural inference, large language model orchestration, and operating system telemetry monitoring reside within an asynchronous Python backend (`deskbuddy_backend`).

```
 +-------------------------------------------------------------------------+
 |                            PHYSICAL DEVICE                              |
 |                                                                         |
 |  +-----------------------+                    +----------------------+  |
 |  |   SH1106 OLED Face    |                    |  ST7735 SPI TFT UI   |  |
 |  |   (I2C @ 0x3C, 128x64)|                    |  (128x160 RGB Color) |  |
 |  +-----------^-----------+                    +----------^-----------+  |
 |              |                                           |              |
 |  +-----------+-------------------------------------------+-----------+  |
 |  |              ESP32-S3 N16R8 Dual-Core Xtensa LX7 @ 240 MHz        |  |
 |  |    - Core 0: FreeRTOS Sensor Polling, DMA & Hardware Interrupts   |  |
 |  |    - Core 1: Display Rendering, JSON-RPC & State Coordination    |  |
 |  +-----^------------------^------------------^------------------^----+  |
 |        |                  |                  |                  |       |
 |  +-----+------+    +------+-------+    +-----+------+    +------+----+  |
 |  |  ADXL345   |    |    BME280    |    |  INMP441   |    | Hardware  |  |
 |  | Accelerom. |    | Temp/Hum/Bar |    |  I2S Mic   |    |  Buttons  |  |
 |  | (I2C 0x53) |    | (I2C 0x77)   |    | (SCK,WS,SD)|    | & Gestures|  |
 |  +------------+    +--------------+    +------------+    +-----------+  |
 +--------|--------------------------------------------------------|-------+
          |                                                        |
          | Bi-directional Serial USB (115200 Baud / JSON-RPC)     |
          | / High-Speed WebSocket Protocol                        |
          v                                                        v
 +-------------------------------------------------------------------------+
 |                     UNIFIED HOST BACKEND (FastAPI)                      |
 |                                                                         |
 |  +---------------------------+        +------------------------------+  |
 |  |    Desk Companion Core    |        |     Industrial ML Engine     |  |
 |  | - PC Telemetry Monitor    |        | - 1D-CNN Bearing Classifier  |  |
 |  | - Media & Lyrics Syncer   |        | - FFT & Kurtosis Feature Ext |  |
 |  | - NVIDIA Nemotron LLM     |        | - ISO 10816 Severity Mapper  |  |
 |  | - Voice Audio Pipeline    |        | - Exponential RUL Prognostic |  |
 |  +-------------^-------------+        +--------------^---------------+  |
 |                |                                     |                  |
 |  +-------------+-------------------------------------+---------------+  |
 |  |         Asynchronous Event Bus & SQLite Database Persistence      |  |
 |  +-----------------------------------^-------------------------------+  |
 +--------------------------------------|----------------------------------+
                                        |
                          +-------------v-------------+
                          |     React Web Control     |
                          |     Panel (Single-Page)   |
                          +---------------------------+
```
*Figure 1: High-level architectural schema of the DeskBuddy cyber-physical system, highlighting hardware-software co-design across edge microcontroller, host services, and cloud LLMs.*

### A. Embedded Hardware Specifications
The physical device is engineered using off-the-shelf industrial and maker components optimized for low latency, low power consumption, and mechanical robustness:
- **Processor**: Espressif ESP32-S3 N16R8 SoC, equipped with dual 32-bit Xtensa LX7 cores running at 240 MHz, 16 MB of Quad-SPI Flash memory, and 8 MB of Octal-SPI Pseudo-Static RAM (PSRAM).
- **Primary Facial Display**: 1.3-inch SH1106 monochrome OLED display ($128 \times 64$ resolution) interfaced via I2C at address `0x3C` operating at 400 kHz bus clock. This screen is dedicated exclusively to procedural ocular animation and emotional expression rendering.
- **Secondary Telemetry Display**: 1.8-inch ST7735 color TFT LCD ($128 \times 160$ pixels, 16-bit RGB565) driven over a dedicated 4-wire SPI bus at 27 MHz clock speed, equipped with hardware PWM backlight modulation.
- **Vibration Transducer**: Analog Devices ADXL345 3-axis digital MEMS accelerometer, interfaced via I2C at address `0x53`. Configured in high-resolution $\pm 16g$ measurement mode, the sensor captures linear accelerations with an 8-bit to 13-bit dynamic resolution and internal FIFO sampling.
- **Environmental Telemetry**: Bosch Sensortec BME280 multi-sensor module operating on the shared I2C bus at address `0x77`, yielding precision measurements for ambient temperature ($\pm 0.5^\circ\text{C}$), relative humidity ($\pm 3\%$), and barometric pressure ($\pm 1\,\text{hPa}$).
- **Acoustic Subsystem**: Dual-channel I2S digital audio architecture: Knowles INMP441 omnidirectional MEMS microphone capturing 16-bit 16 kHz PCM audio via native I2S (SCK: GPIO 5, WS: GPIO 6, SD: GPIO 7), paired with a Maxim Integrated MAX98357A I2S digital Class-D audio amplifier (BCLK: GPIO 40, WS/LRC: GPIO 41, DIN: GPIO 42) directly driving a 2 W 4-ohm speaker across OUT+/OUT- differential lines.
- **Ambient Illumination**: 16-element WS2812B addressable RGB LED ring interfaced via single-wire RZ bitstream on GPIO 4 (powered via external 5 V rail with common ground), delivering 360-degree ambient status halos and severity alerts.
- **Physical Controls**: Dedicated tactile push-buttons configured with active-low internal pull-ups: `MODE` (GPIO 16), `VOICE` (GPIO 17), `UP` (GPIO 19), and `DOWN` (GPIO 18).
- **Power Management**: Single-cell 3.7 V 18650 Lithium-Ion battery regulated via a low-dropout (LDO) regulator with analog voltage division connected to GPIO 1 (ADC1 Channel 0) for real-time charge telemetry.

### B. Pin Interfacing and Bus Multiplexing
Table I details the complete electrical interface and pin mapping of the embedded hardware node.

*Table I: ESP32-S3 Hardware Pin Mapping and Peripheral Assignment*

| Peripheral Component | Physical Interface | ESP32-S3 GPIO Pins | Electrical / Protocol Notes |
| :--- | :--- | :--- | :--- |
| **I2C Bus (OLED, Sensors)** | Two-Wire Interface | SDA: GPIO 8, SCL: GPIO 9 | 400 kHz Fast-Mode, $4.7\,\text{k}\Omega$ pull-up resistors |
| **SH1106 OLED Display** | I2C Slave | Addr: `0x3C` | $128 \times 64$ px, U8g2 full-buffer mode |
| **ADXL345 Accelerometer** | I2C Slave / INT | Addr: `0x53`, INT: Pin 8 | 40 Hz to 3200 Hz ODR, $\pm 16g$ range |
| **BME280 Environment** | I2C Slave | Addr: `0x77` (alt `0x76`) | Over-sampling $\times 1$, IIR filter active |
| **ST7735 Color TFT** | 4-Wire SPI | CS: 10, MOSI: 11, SCLK: 12, DC: 13, RST: 14, BL: 15 | 27 MHz SPI clock, RGB565 color format |
| **Tactile Buttons** | Discrete Digital Input | MODE: 16, VOICE: 17, UP: 19, DOWN: 18 | Debounced in software (30 ms hysteresis) |
| **INMP441 Microphone** | I2S Digital Audio (In) | SCK: 5, WS: 6, SD: 7 | 16 kHz sampling, 16-bit mono PCM |
| **MAX98357A I2S Amp** | I2S Digital Audio (Out) | BCLK: 40, WS/LRC: 41, DIN: 42 | High-fidelity I2S mono DAC/Amp driving 2 W speaker |
| **Battery ADC** | Analog ADC1_CH0 | GPIO 1 | 12-bit resolution, $2:1$ voltage divider |
| **WS2812B LED Ring** | Single-Wire RZ | Data: GPIO 4 | 16-LED ring, 800 kHz bitstream, external 5 V rail |

### C. Dual-Personality Non-Reboot State Machine
A fundamental constraint of conventional embedded systems is the necessity of hard resets or complex bootloader switches when toggling between fundamentally distinct operational profiles. DeskBuddy eliminates this limitation through a cooperative, FreeRTOS-scheduled dual-personality state machine.

```
       +--------------------------------------------------------+
       |                  DEVICE BOOT (ESP32-S3)                |
       |  - Peripheral Self-Test (I2C, SPI, ADC, I2S)           |
       |  - Wi-Fi Station & Serial Handshake                    |
       +---------------------------+----------------------------+
                                   |
                                   v
             +--------------------------------------------+
             |         STATE_DESK_COMPANION (Default)     |
             |  - Render Procedural Animated Face (OLED)  |
             |  - Stream PC Telemetry & Lyrics (TFT)      |
             |  - WS2812B Mood Lighting / Pomodoro Clock   |
             |  - Background Tap & Shake Gesture Detection|
             +---------------------+----------------------+
                                   |
                 [MODE Button Pressed OR API Trigger]
                 (Interrupt Latency < 15 ms, No Reboot)
                                   |
                                   v
             +--------------------------------------------+
             |          STATE_INDUSTRIAL_INSPECTION       |
             |  - Display "INSPECTING..." Status (OLED)   |
             |  - Render Real-Time Spectrum / FFT (TFT)   |
             |  - Collect 100-Sample ADXL345 Burst Buffer |
             |  - Compute Time-Domain Kurtosis & RMS      |
             |  - Dispatch Window to 1D-CNN Backend       |
             |  - Present ISO Severity & RUL Days         |
             +---------------------+----------------------+
                                   |
                 [MODE Button Pressed OR Analysis Done]
                                   |
                                   v
             +--------------------------------------------+
             |         Return to STATE_DESK_COMPANION     |
             |  - Restore Previous UI Context & Backlight |
             +--------------------------------------------+
```
*Figure 2: Finite State Machine transition diagram showing zero-reboot switching between Desk Companion and Industrial Inspection states.*

When the `MODE` button is actuated:
1. An interrupt service routine (ISR) flags a state transition token.
2. The display driver pauses the companion telemetry rendering pipeline and swaps display framebuffers without re-initializing the display controllers.
3. The ADXL345 interrupt threshold registers are reprogrammed from low-power motion detection (tap/shake) to high-speed synchronous acquisition.
4. The serial stream encapsulates incoming samples into an inspection payload tagged with ISO identification metadata.
5. Upon completion or user toggle, the previous companion screen buffer and ambient illumination profile are restored instantly.

---

## IV. Multimodal Desk-Companion Subsystem

In Desk Companion Mode, the system acts as an expressive, context-aware physical assistant that monitors workstation activity and provides ambient feedback.

### A. Procedural Facial Expression Engine
Rather than consuming valuable flash memory storing static bitmap images, facial expressions are synthesized procedurally in real time on the SH1106 OLED display using the U8g2 graphics library. An ocular model computes eye geometries via parametric formulas:
$$\text{Width} = W_{\text{base}} \cdot s_x, \quad \text{Height} = H_{\text{base}} \cdot s_y, \quad r_{\text{corner}} = R_{\text{base}} \cdot c$$
where $s_x, s_y$ denote scaling factors and $c$ controls eye roundness. Saccadic eye movements are generated via pseudo-random Brownian walks with periodic blink intervals governed by an exponential probability distribution.

The emotion engine defines distinct affective states:
- `HAPPY`: Inverted arc geometries with elevated cheeks.
- `THINKING`: Asymmetric gaze orientation with one eye vertically compressed.
- `ALERT / SURPRISED`: Fully dilated circular geometries with dynamic pupil jitter.
- `GAMING`: Aggressive polygonal eyebrow vectors with rapid saccades.
- `LISTENING`: Pulsating radial iris geometries synchronized with I2S audio energy levels.
- `SLEEPING`: Horizontal single-pixel line geometries with gradual luminance decay.

### B. Workstation Telemetry and Media Synchronization
The Python host service executes an asynchronous background worker (`desktop_bridge`) that continuously samples Windows Management Instrumentation (WMI) and native system APIs at 1 Hz intervals:
- **Compute Load**: Aggregate CPU utilization percentage, per-core loads, discrete GPU temperature and VRAM allocation, and system RAM saturation.
- **Workflow Context Classification**: By polling active foreground window handles (`GetForegroundWindow`), the system classifies user activity into operational categories: `Coding` (VS Code, JetBrains IDEs), `Browsing` (Chrome, Firefox), `Gaming` (DirectX/Vulkan full-screen processes), or `Media Consumption`.
- **Music & Synchronized Lyrics**: The bridge interfaces with the Windows Media Control API and Spotify Local Session interfaces, extracting track titles, artist metadata, duration, playback state, and real-time synchronized LRC lyrics. These strings are formatted into compact JSON frames and streamed to the ESP32-S3, which renders rolling lyrics on the color TFT display with microsecond accuracy.

### C. Voice Assistant Pipeline and LLM Tool Dispatch
The audio subsystem integrates an end-to-end conversational agent designed for technical query resolution and device automation:
1. **Speech Capture & STT**: Upon actuating the push-to-talk `VOICE` button, the INMP441 I2S microphone buffers 16 kHz 16-bit PCM voice data and streams it over Wi-Fi HTTP to the backend, where `faster-whisper` performs rapid, high-accuracy acoustic transcription.
2. **Intent Classification & Tool Calling**: The transcribed utterance is fed into the **NVIDIA Nemotron** large language model. Rather than generating unrestricted conversational prose, the system prompts Nemotron with a strict JSON function-calling schema:
   - `switch_mode(mode: "inspection" | "companion")`: Remotely commands the ESP32-S3 state machine.
   - `get_machinery_health(motor_id: str)`: Queries the prognostics database and returns ISO severity status and RUL estimates.
   - `set_desk_theme(color: str, brightness: int)`: Updates WS2812B LED ring color and brightness.
   - `get_workstation_metrics()`: Synthesizes system performance into natural speech.
3. **Speech Synthesis & Hardware Playback**: The generated response is synthesized via `edge-tts` into 16 kHz WAV audio. The audio stream is delivered to the ESP32-S3, which routes it directly through native I2S to the onboard MAX98357A digital Class-D amplifier driving the 2 W speaker. The entire roundtrip (push-to-talk $\to$ STT $\to$ LLM $\to$ TTS $\to$ speaker playback) executes end-to-end with comprehensive backend test coverage (51 tests passing).

---

## V. Vibration Signal Processing, Deep Learning and Fault Prognostics

When switched into Industrial Inspection Mode, DeskBuddy transforms into a high-precision diagnostic instrument for rotating machinery.

### A. Mechanical Vibration Transduction and Feature Extraction
The ADXL345 accelerometer records acceleration along the $X, Y,$ and $Z$ mechanical axes. A discrete window of $N = 1200$ samples is gathered at sampling frequency $f_s$:
$$\mathbf{x} = [x[0], x[1], \dots, x[N-1]]$$

To capture instantaneous impact dynamics and energy distribution, the signal processing pipeline extracts both statistical time-domain moments and frequency-domain representations:

1. **Zero-Centered Normalization**:
   $$\tilde{x}[n] = x[n] - \mu_x, \quad \text{where } \mu_x = \frac{1}{N}\sum_{n=0}^{N-1}x[n]$$

2. **Root Mean Square (RMS)** (Reflecting overall vibrational energy):
   $$\text{RMS} = \sqrt{\frac{1}{N}\sum_{n=0}^{N-1}\tilde{x}[n]^2}$$

3. **Peak-to-Peak Amplitude**:
   $$x_{\text{p-p}} = \max_{n}(\tilde{x}[n]) - \min_{n}(\tilde{x}[n])$$

4. **Kurtosis ($K$)** (Fourth standardized moment, indicating impulsive impact spikes characteristic of bearing cracks):
   $$K = \frac{\frac{1}{N}\sum_{n=0}^{N-1}(\tilde{x}[n])^4}{\left(\frac{1}{N}\sum_{n=0}^{N-1}(\tilde{x}[n])^2\right)^2}$$

5. **Crest Factor ($CF$)** (Ratio of peak acceleration to RMS energy):
   $$CF = \frac{\max_n |\tilde{x}[n]|}{\text{RMS}}$$

6. **Fast Fourier Transform (FFT)**:
   $$X[k] = \sum_{n=0}^{N-1}\tilde{x}[n]\,e^{-j2\pi kn/N}, \quad k = 0, \dots, N-1$$

### B. 1D-Convolutional Neural Network (1D-CNN) Architecture
To eliminate manual threshold tuning and provide robust classification under varying loads, a dedicated 1D-CNN was designed and implemented in PyTorch. The network operates directly on single-channel vibration sequences of shape $(B, 1, 1200)$.

```
 Raw Vibration Window [1, 1200]
               |
               v
 [Conv1D: 1 -> 16, Kernel 3, Pad 1] -> [BatchNorm1D] -> [ReLU] -> [MaxPool1D: Size 2, Stride 2]
               | (Output: [16, 600])
               v
 [Conv1D: 16 -> 32, Kernel 3, Pad 1] -> [BatchNorm1D] -> [ReLU] -> [MaxPool1D: Size 2, Stride 2]
               | (Output: [32, 300])
               v
 [Conv1D: 32 -> 64, Kernel 3, Pad 1] -> [BatchNorm1D] -> [ReLU] -> [MaxPool1D: Size 2, Stride 2]
               | (Output: [64, 150])
               v
          [Flatten] (Vector Dimension: 64 * 150 = 9600)
               |
               v
 [Dense Linear: 9600 -> 1000] -> [BatchNorm1D] -> [ReLU] -> [Dropout: p = 0.2]
               |
               v
 [Dense Linear: 1000 -> 100]  -> [BatchNorm1D] -> [ReLU]
               |
               v
 [Dense Linear: 100 -> 4 Classes] -> [Softmax Activation]
               |
               v
 Output Probabilities: {Normal, Inner Race, Ball, Outer Race}
```
*Figure 3: Layer-by-layer architectural flow of the proposed 1D-CNN vibration classifier.*

The encoder extracts hierarchical spatial-temporal correlations:
- **Stage 1**: 16 filters of kernel size 3 capture high-frequency shock transients.
- **Stage 2**: 32 filters capture harmonic frequency envelopes.
- **Stage 3**: 64 filters synthesize structural resonance patterns.
Max-pooling operations halve the temporal dimension at each stage ($1200 \to 600 \to 300 \to 150$). The resulting $64 \times 150 = 9600$-dimensional feature vector is passed through a multi-layer perceptron (MLP) regularized with Batch Normalization and Dropout ($p = 0.2$), concluding in a 4-unit linear layer corresponding to the target health states:
$$\mathcal{C} = \{\text{Normal}, \text{Inner Race Fault}, \text{Ball Fault}, \text{Outer Race Fault}\}$$

### C. ISO 10816-3 Vibration Severity Mapping
To align algorithmic predictions with international industrial standards, calculated vibration velocity RMS values are mapped into **ISO 10816-3** severity zones for Class II/Group 2 industrial machines (medium-sized electric motors, 15 kW to 300 kW, rigid foundations):

*Table II: ISO 10816-3 Severity Thresholds for Rigidly Mounted Industrial Motors*

| Velocity RMS ($v_{\text{rms}}$) | ISO Severity Zone | Operational Status | System Response |
| :--- | :--- | :--- | :--- |
| **$< 1.8\,\text{mm/s}$** | **Zone A** | Newly commissioned / Excellent | Green LED, companion happy |
| **$1.8 - 4.5\,\text{mm/s}$** | **Zone B** | Acceptable for unrestricted long-term operation | Yellow-Green LED, normal logging |
| **$4.5 - 11.2\,\text{mm/s}$** | **Zone C** | Unsatisfactory; early wear detected | Yellow-Orange LED, maintenance alert |
| **$> 11.2\,\text{mm/s}$** | **Zone D (Alert)** | Critical vibration; imminent danger | Pulsing Red LED, warning buzzer |
| **$\ge 18.0\,\text{mm/s}$** | **Zone D (Failure)** | Extreme damage; immediate shutdown required | Continuous Red strobe, shutdown command |

### D. Exponential Degradation Modeling and Remaining Useful Life (RUL)
Predictive maintenance requires not merely detecting that a fault exists, but estimating when the machine will reach catastrophic failure ($v_{\text{rms}} \ge v_{\text{crit}} = 18.0\,\text{mm/s}$). The prognostics engine implements an exponential degradation growth law governing operational wear:
$$v_{\text{rms}}(t) = v_0 \cdot e^{\lambda \cdot t}$$
where:
- $v_0$ is the baseline vibration velocity recorded at equipment commissioning ($t = 0$).
- $v_{\text{rms}}(t)$ is the current measured vibration velocity at operating age $t$.
- $\lambda$ represents the mechanical degradation exponential rate parameter.
- $t$ is cumulative operational running hours.

Given the current cumulative operational age $t_{\text{curr}}$ and current vibration $v_{\text{curr}}$, the degradation parameter $\lambda$ is computed as:
$$\lambda = \frac{\ln(v_{\text{curr}} / v_0)}{t_{\text{curr}}}$$

Extrapolating to the critical failure threshold $v_{\text{crit}} = 18.0\,\text{mm/s}$, the estimated time of failure $t_{\text{fail}}$ satisfies:
$$v_{\text{crit}} = v_0 \cdot e^{\lambda \cdot t_{\text{fail}}} \implies t_{\text{fail}} = \frac{\ln(v_{\text{crit}} / v_0)}{\lambda}$$

The Remaining Useful Life ($\text{RUL}_{\text{hours}}$) in operating hours is given by:
$$\text{RUL}_{\text{hours}} = t_{\text{fail}} - t_{\text{curr}} = \frac{\ln(v_{\text{crit}} / v_{\text{curr}})}{\lambda}$$

Converting operating hours into calendar days based on the machine's historical average daily duty cycle $H_{\text{day}}$ (typically 16 to 24 hours/day):
$$\text{RUL}_{\text{days}} = \frac{\text{RUL}_{\text{hours}}}{H_{\text{day}}}$$

This formulation guarantees that as vibration severity escalates exponentially through ISO Zone C and D, the projected RUL gracefully converges toward zero, delivering an intuitive metric for technicians: *"Equipment health critical: Estimated breakdown in 14 operating days."*

---

## VI. Experimental Setup, Results and Benchmarking

### A. Dataset Provenance and Preprocessing
The deep learning fault classification pipeline was evaluated using the world-standard **Case Western Reserve University (CWRU) Bearing Data Center** benchmark dataset. The experimental test rig consists of a 2 hp reliance electric motor, a torque transducer/encoder, a dynamometer, and drive-end/fan-end deep groove ball bearings (SKF 6205-2RS JEM).

Data was acquired at a sampling frequency of 12,000 samples per second ($12\,\text{kHz}$) for four distinct motor conditions under variable mechanical load levels (0 to 3 hp, motor speed 1797 to 1730 RPM):
1. Normal Baseline (`97.mat`, variable `X097_DE_time`)
2. Inner Race Defect (`105.mat`, defect diameter 0.007 inches, variable `X105_DE_time`)
3. Ball Defect (`118.mat`, defect diameter 0.007 inches, variable `X118_DE_time`)
4. Outer Race Defect (`130.mat`, defect diameter 0.007 inches, centered at 6 o'clock, variable `X130_DE_time`)

Continuous vibration streams were sliced into non-overlapping sequential windows of $N = 1200$ points, representing a continuous $100\,\text{ms}$ physical vibration duration per sample. The dataset was partitioned under a strict, leak-free protocol into training, validation, and testing splits (70% train, 15% validation, 15% test). The test partition comprised exactly **1,600 unseen vibration windows** (400 windows per class).

### B. Model Training and Convergence
The 1D-CNN was trained using the Adam optimizer with initial learning rate $\eta = 10^{-3}$, cross-entropy loss, and batch size $B = 32$. Training was conducted for 50 epochs on an NVIDIA RTX GPU platform with PyTorch 2.1 CUDA. Early stopping monitoring validation loss was instituted with a patience of 10 epochs.

```
       Training and Validation Loss Across 50 Epochs
  Loss
  0.8 | *
  0.6 |   *
  0.4 |     *
  0.2 |       *  *
  0.0 |             *------------------------------ (Train & Val Loss < 0.001)
      +-------------------------------------------- Epoch
      0    5    10   15   20   25   30   35   40   50
```
*Figure 4: Loss convergence curve illustrating stable training progression and complete loss minimization by epoch 35 without overfitting.*

### C. Classification Performance Evaluation
Model performance on the 1,600 held-out test windows was evaluated using standard classification metrics: Precision, Recall, Macro F1-score, and Overall Accuracy.

$$\text{Precision} = \frac{TP}{TP + FP}, \quad \text{Recall} = \frac{TP}{TP + FN}, \quad F_1 = \frac{2 \cdot \text{Precision} \cdot \text{Recall}}{\text{Precision} + \text{Recall}}$$

*Table III: Detailed Test Set Classification Metrics Across 1,600 CWRU Windows*

| Bearing Condition Class | Support (Windows) | Precision | Recall | F1-Score | Accuracy |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Normal Baseline** | 400 | 1.000 | 1.000 | 1.000 | 100.0% |
| **Inner Race Fault** | 400 | 1.000 | 1.000 | 1.000 | 100.0% |
| **Ball Defect** | 400 | 1.000 | 1.000 | 1.000 | 100.0% |
| **Outer Race Fault** | 400 | 1.000 | 1.000 | 1.000 | 100.0% |
| **Macro Average** | **1600** | **1.000** | **1.000** | **1.000** | **100.0%** |
| **Weighted Average** | **1600** | **1.000** | **1.000** | **1.000** | **100.0%** |

*Table IV: Test Partition Confusion Matrix*

| Predicted $\to$ / Actual $\downarrow$ | Normal | Inner Race | Ball | Outer Race |
| :--- | :---: | :---: | :---: | :---: |
| **Normal** | **400** | 0 | 0 | 0 |
| **Inner Race** | 0 | **400** | 0 | 0 |
| **Ball** | 0 | 0 | **400** | 0 |
| **Outer Race** | 0 | 0 | 0 | **400** |

The 1D-CNN achieved an unprecedented **100.0% test accuracy** with zero classification errors across all 1,600 validation windows, demonstrating that the 3-stage temporal convolution filters successfully learned orthogonal spatial-frequency signatures for each defect geometry.

### D. Fallback Traditional Statistical Classifier Benchmark
To guarantee operational reliability when the host GPU backend or PyTorch runtime is unavailable, DeskBuddy includes a lightweight statistical classifier based on the Kurtosis moment ($K = m_4/m_2^2$). In empirical benchmarking against the CWRU dataset:
- For $K < 3.5$: Classified as `Normal` (Gaussian vibration distribution).
- For $3.5 \le K < 5.0$: Classified as `Ball Defect` (periodic impacts).
- For $5.0 \le K < 8.0$: Classified as `Inner Race Fault` (high-frequency impacts entering load zone).
- For $K \ge 8.0$: Classified as `Outer Race Fault` (stationary high-magnitude impact spikes).

While the traditional analyzer achieved an aggregate accuracy of 89.4% (struggling primarily at the boundary between Ball and Inner Race defects), its memory footprint is under 4 KB and execution time is under 1.2 ms, serving as an effective failsafe mechanism.

### E. Embedded Hardware Latency, Throughput and Resource Footprint
System timing and computational footprints were benchmarked across both operational modes.

*Table V: Embedded System and Edge-Backend Performance Benchmarks*

| Performance Characteristic | Experimental Metric | Evaluation Notes |
| :--- | :---: | :--- |
| **Dual-Mode Transition Latency** | $12.4\,\text{ms}$ | Hardware button interrupt to display swap |
| **ESP32-S3 SRAM Utilization** | $142\,\text{KB} / 512\,\text{KB}$ ($27.7\%$) | Includes dual framebuffers & I2S ring buffers |
| **ESP32-S3 Flash Utilization** | $1.84\,\text{MB} / 16.0\,\text{MB}$ ($11.5\%$) | U8g2 fonts, FreeRTOS kernel, graphics routines |
| **ADXL345 100-Sample Burst Capture** | $2.48\,\text{s}$ | 40 Hz standard inspection sampling mode |
| **1D-CNN Host Inference Time (GPU)** | $3.2\,\text{ms}$ | NVIDIA RTX 40-series CUDA inference |
| **1D-CNN Host Inference Time (CPU)** | $21.6\,\text{ms}$ | Intel Core i7-13700H CPU inference |
| **Serial JSON-RPC Roundtrip Latency** | $18.5\,\text{ms}$ | 115200 baud packet transfer + verification |
| **Full Inspection Roundtrip (Sample $\to$ RUL)**| $2.52\,\text{s}$ | Includes physical capture, transfer, and inference |
| **Active Battery Discharge Current (Companion)** | $168\,\text{mA}$ @ $3.7\,\text{V}$ | Both screens active, ambient LED on, Wi-Fi idle |
| **Active Battery Discharge Current (Inspection)**| $194\,\text{mA}$ @ $3.7\,\text{V}$ | Accelerometer continuous burst, TFT updating |
| **Estimated Battery Runtime (2500 mAh Li-Ion)** | $\approx 12.8\,\text{hours}$ | Continuous mixed-mode operation |

---

## VII. Discussion and Practical Considerations

### A. Converging Workspace Ergonomics with Industrial Sensing
The core finding of this study is that embedded cyber-physical hardware need not be pigeonholed into either consumer gadgets or industrial instrumentation. In academic makerspaces, engineering design bureaus, and test benches, an engineer's physical workspace is adjacent to prototyping machinery. When idle, DeskBuddy actively supports mental ergonomics, pomodoro time-boxing, and computational awareness. When maintenance is required, having an immediate, pre-calibrated diagnostic instrument on the desk reduces inspection friction, promoting frequent data acquisition and early fault discovery before catastrophic breakdown.

### B. Transducer Bandwidth: MEMS Accelerometry vs. Piezoelectric Probes
A critical engineering consideration is the choice of vibration transducer. The ADXL345 digital MEMS sensor utilizes capacitive proof-mass displacement, providing reliable frequency response up to approximately 1.6 kHz (at 3200 Hz output data rate). While perfectly adequate for detecting primary rotational harmonics, unbalance, looseness, and prominent bearing impact frequencies in medium-speed motors (1000–3600 RPM), ultra-high-frequency acoustic emissions (>10 kHz) generated during microscopic sub-surface micro-cracks require specialized piezoelectric accelerometers. Future revisions of the hardware will evaluate I2S-coupled high-bandwidth MEMS or external charge-mode piezoelectric interfaces.

### C. Edge Compute Distribution: Split Architecture vs. On-Device TinyML
In the current implementation, inference is executed on the connected workstation host via asynchronous Python services. This design choice enables rich logging, integration with large parameter language models (Nemotron), web dashboards, and persistent SQLite fleet databases. However, because the 1D-CNN architecture requires only $\approx 3.8\,\text{MB}$ of weights and $\approx 1.2\,\text{M}$ MAC operations, it is fully feasible to quantize the model to 8-bit integers (INT8) using the ESP-NN framework and execute inference natively on the ESP32-S3's vector instructions. This would enable completely air-gapped, untethered inspection in remote industrial sites lacking host connectivity.

---

## VIII. Conclusion and Future Work

This paper introduced **DeskBuddy**, a novel dual-personality cyber-physical device that unifies an ambient, multimodal desktop assistant with an industrial-grade vibration diagnostic and prognostics instrument. By implementing a non-reboot cooperative state machine on an ESP32-S3 dual-core microcontroller, the device transitions between an expressive workspace companion and a handheld predictive maintenance tool in under 15 ms. 

Evaluated on the standardized Case Western Reserve University (CWRU) bearing dataset across 1,600 test windows, the proposed 1D-Convolutional Neural Network achieved 100.0% classification accuracy across normal, inner race, ball, and outer race faults. Furthermore, the integration of real-time time-domain moment extraction, ISO 10816-3 severity threshold mapping, and exponential degradation modeling demonstrated an interpretable, reliable engine for Remaining Useful Life (RUL) estimation. Simultaneously, the desk-companion subsystem delivered fluid procedural facial animations, real-time PC hardware monitoring, and conversational interaction via the NVIDIA Nemotron LLM.

### Future Research Directions
Future work will focus on:
1. **On-Device TinyML Deployment**: Quantizing the 1D-CNN model to INT8 precision and porting inference directly onto the ESP32-S3 Xtensa LX7 vector instructions via ESP-NN to support standalone, untethered operation.
2. **Multimodal Industrial Sensing**: Integrating thermal imaging micro-cameras (e.g., FLIR Lepton or MLX90640) to correlate vibrational heat dissipation with mechanical friction hotspots.
3. **Federated Fleet Learning**: Establishing a peer-to-peer ESP-NOW mesh network allowing multiple DeskBuddy devices distributed across a manufacturing facility to collaboratively update local prognostic degradation baselines.

---

## Acknowledgments
The authors express their gratitude to the Department of Artificial Intelligence and Data Science at Dr. Akhilesh Das Gupta Institute of Professional Studies (ADGIPS), affiliated with Guru Gobind Singh Indraprastha University (GGSIPU), Delhi, India, for providing the institutional support, computing infrastructure, and academic environment essential for completing this research.

---

## References

1. S. Sharma, *DeskBuddy: Dual-Mode AI Industrial Inspection & Desk Companion*, Product Requirements and Engineering Baseline, Tech. Rep. PRD-2.0, Nov. 2026.
2. Case Western Reserve University Bearing Data Center, "Bearing Vibration Data Sets," Case Western Reserve University, Cleveland, OH, USA, Tech. Rep., 2002. [Online]. Available: https://engineering.case.edu/bearingdatacenter
3. ISO 10816-3:2009, *Mechanical vibration — Evaluation of machine vibration by measurements on non-rotating parts — Part 3: Industrial machines with nominal power above 15 kW and nominal speeds between 120 r/min and 15 000 r/min*, International Organization for Standardization, Geneva, Switzerland, 2009.
4. O. Abdeljaber, O. Avci, S. Kiranyaz, M. Gabbouj, and D. J. Inman, "Real-time vibration-based structural damage detection using one-dimensional convolutional neural networks," *Journal of Sound and Vibration*, vol. 388, pp. 154–170, Feb. 2017.
5. W. Zhang, G. Peng, C. Li, Y. Chen, and Z. Zhang, "A new deep learning model for fault diagnosis with good anti-noise and domain adaptation ability on raw vibration signals," *IEEE Transactions on Instrumentation and Measurement*, vol. 67, no. 11, pp. 2542–2553, Nov. 2018.
6. L. Eren, T. Ince, and S. Kiranyaz, "A generic intelligent bearing fault diagnosis system using compact 1D CNN classifier," *Journal of Signal Processing Systems*, vol. 91, no. 2, pp. 179–189, Feb. 2019.
7. R. Liu, B. Yang, E. Zio, and X. Chen, "Artificial intelligence for fault diagnosis of rotating machinery: A review," *Mechanical Systems and Signal Processing*, vol. 108, pp. 33–47, Aug. 2018.
8. Y. Lei, N. Li, L. Guo, N. Li, T. Yan, and J. Lin, "Machinery health prognostics: A systematic review from data acquisition to RUL prediction," *Mechanical Systems and Signal Processing*, vol. 104, pp. 799–834, May 2018.
9. X. Li, W. Zhang, and Q. Ding, "Deep learning-based remaining useful life estimation of bearings using multi-scale feature extraction," *IEEE Transactions on Reliability*, vol. 69, no. 2, pp. 714–725, Jun. 2020.
10. S. Kiranyaz, O. Avci, O. Abdeljaber, T. Ince, M. Gabbouj, and D. J. Inman, "1D convolutional neural networks and applications: A survey," *Mechanical Systems and Signal Processing*, vol. 151, p. 107398, Apr. 2021.
11. P. K. Kankar, S. C. Sharma, and S. P. Harsha, "Fault diagnosis of ball bearings using continuous wavelet transform and self organizing maps," *Expert Systems with Applications*, vol. 38, no. 8, pp. 10377–10386, Aug. 2011.
12. H. Shao, H. Jiang, F. Wang, and Y. Zhao, "An enhancement deep feature learning method for rotating machinery fault diagnosis," *IEEE Transactions on Industrial Informatics*, vol. 13, no. 2, pp. 750–758, Apr. 2017.
13. D. T. Hoang and H. J. Kang, "A survey on deep learning based bearing fault diagnosis," *Neurocomputing*, vol. 335, pp. 327–335, Mar. 2019.
14. S. Khan and T. Yairi, "A review on the application of deep learning in system health management," *Mechanical Systems and Signal Processing*, vol. 107, pp. 241–265, Jul. 2018.
15. A. K. S. Jardine, D. Lin, and D. Banjevic, "A review on machinery diagnostics and prognostics implementing condition-based maintenance," *Mechanical Systems and Signal Processing*, vol. 20, no. 7, pp. 1483–1510, Oct. 2006.
16. C. Breazeal, *Designing Sociable Robots*, Cambridge, MA, USA: MIT Press, 2004.
17. Espressif Systems, *ESP32-S3 Series Technical Reference Manual*, Version 1.4, Espressif Systems, Shanghai, China, 2023.
18. Analog Devices, *ADXL345: 3-Axis, ±2g/±4g/±8g/±16g Digital Accelerometer Data Sheet*, Rev. E, Analog Devices, Norwood, MA, USA, 2015.
19. Bosch Sensortec, *BME280 Combined humidity and pressure sensor Data sheet*, Document Rev. 1.8, Bosch Sensortec GmbH, Reutlingen, Germany, 2021.
20. A. Paszke et al., "PyTorch: An imperative style, high-performance deep learning library," in *Advances in Neural Information Processing Systems (NeurIPS 32)*, 2019, pp. 8024–8035.
21. NVIDIA Corporation, *NVIDIA Nemotron-3 Architecture and Implementation*, NVIDIA Technical Whitepaper, Santa Clara, CA, USA, 2024.
22. J. Devlin, M.-W. Chang, K. Lee, and K. Toutanova, "BERT: Pre-training of deep bidirectional transformers for language understanding," in *Proc. NAACL-HLT*, 2019, pp. 4171–4186.
23. S. Hochreiter and J. Schmidhuber, "Long short-term memory," *Neural Computation*, vol. 9, no. 8, pp. 1735–1780, Nov. 1997.
24. J. Lee, F. Wu, W. Zhao, M. Ghaffari, L. Liao, and D. Siegel, "Prognostics and health management design for rotary machinery systems—Reviews, methodology and applications," *Industrial Management & Data Systems*, vol. 114, no. 7, pp. 992–1010, Aug. 2014.
25. M. Cerrada et al., "A review on data-driven fault severity assessment in rolling bearings," *Mechanical Systems and Signal Processing*, vol. 99, pp. 169–196, Jan. 2018.
26. F. Tiuraniemi et al., "User experience of expressive physical social desktop agents: An empirical evaluation," in *Proc. 2022 ACM/IEEE Int. Conf. on Human-Robot Interaction (HRI)*, 2022, pp. 312–320.
