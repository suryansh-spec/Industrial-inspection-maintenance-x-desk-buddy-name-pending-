import docx
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, fill_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    tcPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>'))

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

from pathlib import Path

def create_document():
    repo_root = Path(__file__).resolve().parent.parent
    template_path = repo_root / 'docs' / 'research_paper' / 'IRJMETS_OmniDesk_Paper.docx'
    output_path = repo_root / 'docs' / 'research_paper' / 'IRJMETS_OmniDesk_Paper.docx'
    
    doc = docx.Document(str(template_path)) if template_path.exists() else docx.Document()
    
    # Remove existing tables in template body (sample displacement table)
    for t in list(doc.tables):
        t._element.getparent().remove(t._element)

    # Clear existing body paragraphs while preserving section/header properties
    p_elements = [p._p for p in doc.paragraphs]
    for p in p_elements[1:]:
        p.getparent().remove(p)
    
    # We will reuse the first paragraph for the Title
    p_title = doc.paragraphs[0]
    p_title.text = ""
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_title = p_title.add_run("OMNIDESK: A MULTIMODAL DESK-COMPANION AGENT WITH ON-DEMAND EDGE MACHINERY HEALTH DIAGNOSTICS AND FAULT PROGNOSTICS")
    r_title.font.name = "Cambria"
    r_title.font.size = Pt(14)
    r_title.font.bold = True
    p_title.paragraph_format.space_before = Pt(6)
    p_title.paragraph_format.space_after = Pt(6)
    p_title.paragraph_format.line_spacing = 1.15

    # Authors
    p_auth = doc.add_paragraph()
    p_auth.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_auth = p_auth.add_run("Suryansh Sharma*1, Prof. (Dr.) Archana Kumar*2")
    r_auth.font.name = "Cambria"
    r_auth.font.size = Pt(12)
    r_auth.font.bold = True
    p_auth.paragraph_format.space_after = Pt(3)

    # Affiliation 1
    p_aff1 = doc.add_paragraph()
    p_aff1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_aff1 = p_aff1.add_run("*1Department of Artificial Intelligence and Data Science, Dr. Akhilesh Das Gupta Institute of Professional Studies (ADGIPS), New Delhi, Delhi, India.")
    r_aff1.font.name = "Cambria"
    r_aff1.font.size = Pt(11)
    p_aff1.paragraph_format.space_after = Pt(2)

    # Affiliation 2
    p_aff2 = doc.add_paragraph()
    p_aff2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_aff2 = p_aff2.add_run("*2Professor, Department of Artificial Intelligence and Data Science, Dr. Akhilesh Das Gupta Institute of Professional Studies (ADGIPS), New Delhi, Delhi, India.")
    r_aff2.font.name = "Cambria"
    r_aff2.font.size = Pt(11)
    p_aff2.paragraph_format.space_after = Pt(8)

    # Divider line
    p_div1 = doc.add_paragraph()
    p_div1.paragraph_format.space_after = Pt(8)
    pBdr = parse_xml(f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="6" w:space="1" w:color="000000"/></w:pBdr>')
    p_div1._p.get_or_add_pPr().append(pBdr)

    # Helper for Section Heading
    def add_section_heading(text):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(text)
        run.font.name = "Cambria"
        run.font.size = Pt(12)
        run.font.bold = True
        return p

    # Helper for Subheading
    def add_subheading(text):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(3)
        run = p.add_run(text)
        run.font.name = "Cambria"
        run.font.size = Pt(10)
        run.font.bold = True
        return p

    # Helper for Body Paragraph
    def add_body_p(text, bold_prefix=""):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.15
        if bold_prefix:
            r_pre = p.add_run(bold_prefix)
            r_pre.font.name = "Times New Roman"
            r_pre.font.size = Pt(10)
            r_pre.font.bold = True
        run = p.add_run(text)
        run.font.name = "Times New Roman"
        run.font.size = Pt(10)
        return p

    # ABSTRACT
    add_section_heading("ABSTRACT")
    add_body_p(
        "Rotating machinery breakdowns cause severe industrial downtime, yet conventional vibration analyzers remain costly, bulky, and isolated from daily engineering environments. This paper presents OmniDesk, an innovative cyber-physical system integrating an ambient desktop companion with an on-demand predictive maintenance instrument on a unified ESP32-S3 hardware platform. Operating across dual personalities without rebooting, the device provides workspace telemetry, procedural OLED facial biofeedback, ambient lighting, and NVIDIA Nemotron-driven voice assistance during desk hours. Upon actuation, it transitions within 12.4 ms into an industrial vibration analyzer. The diagnostic pipeline introduces ExtensiveCNN, a deep residual 1D-CNN incorporating Squeeze-and-Excitation channel attention, dilated convolutions, and a dedicated spectral FFT branch. Evaluated on 40 Case Western Reserve University (CWRU) bearing recordings under a leak-free recording-level split, ExtensiveCNN achieves 100.0% test accuracy across 2,420 unseen windows on held-out 3 hp operational loads. The spectral branch resolves Outer Race defect confusion, boosting recall from 0% to 100%. Concurrently, a physics-informed prognostics engine integrates exponential degradation, linear trend analysis, and Paris' law crack growth with ISO 10816-3 severity criteria and uncertainty bounds to forecast Remaining Useful Life (RUL). The system demonstrates a reliable, cost-effective paradigm uniting workplace ergonomics with rigorous edge predictive maintenance."
    )

    # Keywords
    p_kw = doc.add_paragraph()
    p_kw.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p_kw.paragraph_format.space_after = Pt(8)
    r_kw_lbl = p_kw.add_run("Keywords: ")
    r_kw_lbl.font.name = "Cambria"
    r_kw_lbl.font.size = Pt(10)
    r_kw_lbl.font.bold = True
    r_kw_val = p_kw.add_run("Bearing Fault Diagnosis, 1D-CNN, Paris' Law, Remaining Useful Life, Cyber-Physical Systems, Edge AI.")
    r_kw_val.font.name = "Cambria"
    r_kw_val.font.size = Pt(10)

    # Divider line
    p_div2 = doc.add_paragraph()
    p_div2.paragraph_format.space_after = Pt(8)
    pBdr2 = parse_xml(f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="6" w:space="1" w:color="000000"/></w:pBdr>')
    p_div2._p.get_or_add_pPr().append(pBdr2)

    # I. INTRODUCTION
    add_section_heading("I.   INTRODUCTION")
    add_body_p(
        "Rotating mechanical equipment, such as induction motors, pumps, gearboxes, and CNC spindles, represents the operational core of manufacturing plants, prototyping labs, and academic fabrication facilities. Rolling-element bearings are subjected to severe cyclic contact stresses, contributing to more than 40% of all induction motor failures. Unplanned mechanical breakdowns result in severe economic losses, production bottlenecks, and workplace safety hazards. Consequently, Condition-Based Maintenance (CBM) relying on vibration diagnostics has become essential for modern Industry 4.0 operations."
    )
    add_body_p(
        "However, existing industrial condition monitoring solutions suffer from acute structural limitations. Commercial vibration data collectors and spectrum analyzers are bulky, highly expensive, closed-source instruments costing several thousands of dollars. As a result, small-scale fabrication units, maker facilities, and university laboratories frequently defer essential vibration inspections. Furthermore, these dedicated tools sit idle in storage cabinets between inspection routes and offer zero utility for everyday engineering desktop workflows. Simultaneously, research developers and engineers spend extended hours at computer workstations enduring cognitive fatigue, fragmented context switching across system dashboards, and high mental stress without ambient ergonomically supportive tools."
    )
    add_body_p(
        "To resolve this operational bifurcation, this research develops OmniDesk, a converged cyber-physical edge system that co-locates an ambient desktop companion with an industrial-grade vibration diagnostic and prognostics instrument on a unified ESP32-S3 hardware platform. During regular workstation hours, OmniDesk functions as an interactive desktop assistant: rendering procedural emotional eye animations on an SH1106 OLED screen, displaying real-time PC performance telemetry on an ST7735 color TFT screen, coordinating ambient notification lighting via a 16-element WS2812B LED ring, and responding to voice queries through an integrated NVIDIA Nemotron LLM audio pipeline."
    )
    add_body_p(
        "When an engineer inspects bench or floor machinery, depressing a dedicated hardware button instantly switches the device into an Industrial Inspection Instrument without triggering a system reboot. The device captures tri-axial acceleration signals through an ADXL345 MEMS sensor, extracts statistical time-domain features, and streams acceleration windows to an asynchronous backend. A deep dual-branch residual network (ExtensiveCNN) combines raw temporal vibrations with an FFT spectral branch, achieving 100.0% test accuracy on 2,420 test windows across held-out motor recordings from the CWRU repository. A multi-model prognostics engine integrates exponential regression, linear trend fitting, and Paris' law fatigue crack propagation with ISO 10816-3 severity standards to project Remaining Useful Life (RUL) with rigorous confidence bounds."
    )

    # II. METHODOLOGY
    add_section_heading("II.   METHODOLOGY")
    add_subheading("Hardware-Software Co-Design")
    add_body_p(
        "OmniDesk is architected around an edge-to-host split paradigm. The physical node is powered by an Espressif ESP32-S3 N16R8 SoC (Dual-Core Xtensa LX7 @ 240 MHz, 16 MB Flash, 8 MB PSRAM). FreeRTOS task scheduling is divided between Core 0 (sensor sampling, DMA, and serial JSON-RPC communications) and Core 1 (display framebuffer generation, ocular animation, and UI state management)."
    )
    add_body_p("Table 1 details the peripheral allocation and electrical pin mapping of the embedded hardware node.")

    # Table 1
    p_t1_lbl = doc.add_paragraph()
    p_t1_lbl.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_t1_lbl = p_t1_lbl.add_run("Table 1. ESP32-S3 Hardware Pin Mapping and Peripheral Assignment")
    r_t1_lbl.font.name = "Cambria"
    r_t1_lbl.font.size = Pt(10)
    r_t1_lbl.font.bold = True
    p_t1_lbl.paragraph_format.space_after = Pt(2)

    table1_data = [
        ["Peripheral Component", "Physical Interface", "ESP32-S3 GPIO Pins", "Electrical / Protocol Notes"],
        ["I2C Bus (OLED, Sensors)", "Two-Wire Interface", "SDA: GPIO 8, SCL: GPIO 9", "400 kHz Fast-Mode, 4.7 kΩ pull-up resistors"],
        ["SH1106 OLED Display", "I2C Slave", "Address 0x3C", "128 × 64 px, U8g2 full-buffer mode"],
        ["ADXL345 Accelerometer", "I2C Slave / INT", "Address 0x53, INT: Pin 8", "40 Hz to 3200 Hz ODR, ±16g dynamic range"],
        ["BME280 Environment", "I2C Slave", "Address 0x77 (alt 0x76)", "Temperature, relative humidity, barometric pressure"],
        ["ST7735 Color TFT", "4-Wire SPI", "CS:10, MOSI:11, SCLK:12, DC:13, RST:14, BL:15", "27 MHz SPI clock, RGB565 color format"],
        ["Tactile Buttons", "Discrete Digital Input", "MODE: 16, VOICE: 17, UP: 19, DOWN: 18", "Active-low internal pull-ups, debounced in software"],
        ["INMP441 Microphone", "I2S Digital In", "SCK: 5, WS: 6, SD: 7", "16 kHz sampling, 16-bit mono PCM"],
        ["MAX98357A I2S Amp", "I2S Digital Out", "BCLK: 40, WS/LRC: 41, DIN: 42", "Class-D mono amplifier driving 2 W 4Ω speaker"],
        ["Battery ADC", "Analog ADC1_CH0", "GPIO 1", "12-bit resolution, 2:1 resistive voltage divider"],
        ["WS2812B LED Ring", "Single-Wire RZ", "Data: GPIO 4", "16-element addressable RGB ring, external 5 V rail"]
    ]

    t1 = doc.add_table(rows=len(table1_data), cols=4)
    t1.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r_idx, row in enumerate(table1_data):
        for c_idx, val in enumerate(row):
            cell = t1.cell(r_idx, c_idx)
            cell.text = val
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if c_idx in [1, 2] else WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            run = p.runs[0]
            run.font.name = "Times New Roman"
            run.font.size = Pt(9)
            if r_idx == 0:
                run.font.bold = True
                set_cell_background(cell, "EAEAEA")
            set_cell_margins(cell, top=60, bottom=60, left=80, right=80)
    
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    add_subheading("Zero-Reboot State Transition Mechanism")
    add_body_p(
        "A critical requirement of the system is instantaneous mode switching without rebooting the microcontroller or terminating active communication sessions. When the physical MODE button is depressed, an interrupt service routine (ISR) triggers a cooperative state token. Display framebuffers are preserved in internal RAM without re-initializing controller chips, ADXL345 registers are reconfigured from low-power tap interrupt mode into high-speed burst measurement, and serial communication channels switch from streaming desktop telemetry to streaming raw vibration records. The full state transition completes in 12.4 ms."
    )

    add_subheading("Multimodal Desk Companion Services")
    add_body_p(
        "In companion mode, the device enhances workstation ergonomics through four coordinated subsystems: (i) Procedural Facial Expression rendering parametric ocular models on the SH1106 OLED using the U8g2 graphics engine with Brownian saccades simulating affective states; (ii) Workstation Telemetry Bridge sampling Windows Management Instrumentation (WMI) at 1 Hz for CPU, GPU core temperature, VRAM saturation, and RAM usage; (iii) Workflow Context & Media Sync tracking active window handles and rendering synchronized Spotify LRC lyrics on the TFT display; and (iv) Voice Assistant Pipeline capturing 16 kHz 16-bit PCM voice data via the INMP441 microphone to faster-whisper STT, routed to NVIDIA Nemotron for tool execution, and synthesized via edge-tts through the MAX98357A I2S Class-D amplifier driving the 2 W speaker."
    )

    # III. MODELING AND ANALYSIS
    add_section_heading("III.   MODELING AND ANALYSIS")
    add_subheading("Signal Conditioning and Feature Extraction")
    add_body_p(
        "Discrete acceleration windows of N = 1024 samples (fs = 12000 Hz, duration ~85.3 ms) captured along three orthogonal axes are zero-centered: x~[n] = x[n] - μx. Time-domain statistical features are extracted in real time: Root Mean Square (RMS) reflecting vibrational energy, Peak-to-Peak amplitude (x_p-p), Kurtosis (K = m4 / m2^2) indicating impulse impact spikes characteristic of bearing spalls, and Crest Factor (CF = Peak / RMS)."
    )

    add_subheading("ExtensiveCNN Architecture with Dual-Branch Spectral Attention")
    add_body_p(
        "To achieve robust classification across variable operational motor loads, the proposed ExtensiveCNN architecture combines a multi-scale dilated residual temporal branch with a Real Fast Fourier Transform (rFFT) spectral branch."
    )
    add_body_p(
        "1. Temporal Residual Backbone: The temporal path ingests normalized 1D sequences of shape (B, 1, 1024). An initial convolutional layer (64 filters, kernel size 7, stride 2) is followed by three residual blocks with increasing dilation factors (d in {1, 2, 4}): y[n] = sum(x[n - d*k] * w[k]). Dilated convolutions exponentially expand the receptive field to capture both high-frequency localized impact transients and low-frequency rotational shaft harmonics without sacrificing temporal resolution."
    )
    add_body_p(
        "2. Squeeze-and-Excitation (SE) Channel Attention: Within each residual block, SE attention recalibrates channel feature responses. Global temporal context is compressed via average pooling: z_c = (1/L)*sum(u_c(i)). The excitation operator models channel-wise dependencies: s = sigmoid(W2 * ReLU(W1 * z)), scaling feature channels as u~_c = s_c * u_c."
    )
    add_body_p(
        "3. Dual-Branch Spectral Fusion: An rFFT converts the 1024-sample window into 513 discrete spectral magnitude bins. A 2-layer perceptron (513 -> 128 -> 64) generates a compact frequency embedding concatenated with the 256-dimensional temporal embedding resulting from Global Average Pooling, creating a 320-dimensional joint feature representation feeding the classification head across {Normal Baseline, Inner Race Fault, Ball Defect, Outer Race Fault}."
    )

    add_subheading("Physics-Informed Multi-Model Prognostics & RUL Engine")
    add_body_p(
        "The prognostics engine in prognostics.py models machine wear progression grounded in ISO 10816-3 severity standards: Zone A (v_rms < 1.8 mm/s, Good), Zone B (1.8 to 4.5 mm/s, Acceptable), Zone C (4.5 to 11.2 mm/s, Warning), and Zone D (v_rms > 11.2 mm/s, Critical Alert; breakdown at v_crit = 18.0 mm/s). The engine implements a triple-path degradation formulation:"
    )
    add_body_p(
        "1. Exponential Degradation Model: v(t) = v_0 * exp(lambda * t) => RUL_exp = max(0, ln(v_crit / v_curr) / lambda)."
    )
    add_body_p(
        "2. Linear Degradation Trend Model: v(t) = v_0 + beta * t => RUL_lin = max(0, (v_crit - v_curr) / beta)."
    )
    add_body_p(
        "3. Paris' Law Crack Growth Model: Fatigue spall propagation follows Paris' power law: da/dN = C*(Delta K)^m => a(t) = a_0 * exp(k_paris * t), yielding RUL_Paris = ln(a_crit / a_curr) / k_paris."
    )
    add_body_p(
        "Linear regression residuals produce residual standard errors (s_e), constructing a 95% confidence interval via the Student's t-distribution. The system selects the Conservative RUL = min(RUL_exp, RUL_lin, RUL_Paris), converted to calendar operating days using the daily duty cycle: RUL_days = RUL_conservative / H_day."
    )

    # IV. RESULTS AND DISCUSSION
    add_section_heading("IV.   RESULTS AND DISCUSSION")
    add_subheading("Experimental Dataset and Leak-Free Evaluation Protocol")
    add_body_p(
        "The machine learning pipeline was trained and benchmarked using 40 complete MAT files from the Case Western Reserve University (CWRU) 12 kHz Drive-End bearing dataset, comprising 4 Normal recordings and 36 fault recordings across three fault diameters (0.007\", 0.014\", 0.021\") under four motor loads (0, 1, 2, 3 hp)."
    )
    add_body_p(
        "To prevent window-level data leakage, a strict recording-level split was enforced: Held-Out Test Set (3 hp Recordings: '100' Normal, '108' Inner, '121' Ball, '133' Outer), Held-Out Validation Set (2 hp Recordings: '99', '172', '188', '200'), and Training Set (32 Recordings: all 0 hp and 1 hp recordings). No individual recording contributed windows to more than one split partition. The test partition comprised 2,420 unseen windows (1,000 Normal, 476 Inner Race, 470 Ball, and 474 Outer Race)."
    )

    add_subheading("Classification Performance")
    add_body_p(
        "ExtensiveCNN-light (1.1M parameters) was trained using AdamW (lr=1e-3, weight decay 1e-4), Cosine Annealing with Warm Restarts, Label Smoothing (eps=0.1), Mixup (alpha=0.2), and AMP FP16 on an NVIDIA GeForce RTX 3060 (CUDA 12.4). Training completed in 53 epochs (best validation model saved at Epoch 40)."
    )

    # Table 2
    p_t2_lbl = doc.add_paragraph()
    p_t2_lbl.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_t2_lbl = p_t2_lbl.add_run("Table 2. Test Classification Performance on 2,420 Held-Out CWRU Windows")
    r_t2_lbl.font.name = "Cambria"
    r_t2_lbl.font.size = Pt(10)
    r_t2_lbl.font.bold = True
    p_t2_lbl.paragraph_format.space_after = Pt(2)

    table2_data = [
        ["Bearing Condition Class", "Support (Windows)", "Precision", "Recall", "F1-Score", "Accuracy"],
        ["Normal Baseline", "1000", "1.000", "1.000", "1.000", "100.0% (1000/1000)"],
        ["Inner Race Fault", "476", "1.000", "1.000", "1.000", "100.0% (476/476)"],
        ["Ball Defect", "470", "1.000", "1.000", "1.000", "100.0% (470/470)"],
        ["Outer Race Fault", "474", "1.000", "1.000", "1.000", "100.0% (474/474)"],
        ["Macro / Weighted Avg", "2420", "1.000", "1.000", "1.000", "100.0% (2420/2420)"]
    ]

    t2 = doc.add_table(rows=len(table2_data), cols=6)
    t2.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r_idx, row in enumerate(table2_data):
        for c_idx, val in enumerate(row):
            cell = t2.cell(r_idx, c_idx)
            cell.text = val
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if c_idx > 0 else WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            run = p.runs[0]
            run.font.name = "Times New Roman"
            run.font.size = Pt(9)
            if r_idx in [0, len(table2_data)-1]:
                run.font.bold = True
                if r_idx == 0:
                    set_cell_background(cell, "EAEAEA")
            set_cell_margins(cell, top=60, bottom=60, left=60, right=60)
    
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    # Table 3
    p_t3_lbl = doc.add_paragraph()
    p_t3_lbl.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_t3_lbl = p_t3_lbl.add_run("Table 3. Test Partition Confusion Matrix Across 2,420 Windows")
    r_t3_lbl.font.name = "Cambria"
    r_t3_lbl.font.size = Pt(10)
    r_t3_lbl.font.bold = True
    p_t3_lbl.paragraph_format.space_after = Pt(2)

    table3_data = [
        ["Predicted -> / Actual v", "Normal", "Inner Race", "Ball", "Outer Race"],
        ["Normal", "1000", "0", "0", "0"],
        ["Inner Race", "0", "476", "0", "0"],
        ["Ball", "0", "0", "470", "0"],
        ["Outer Race", "0", "0", "0", "474"]
    ]
    t3 = doc.add_table(rows=len(table3_data), cols=5)
    t3.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r_idx, row in enumerate(table3_data):
        for c_idx, val in enumerate(row):
            cell = t3.cell(r_idx, c_idx)
            cell.text = val
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if c_idx > 0 else WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            run = p.runs[0]
            run.font.name = "Times New Roman"
            run.font.size = Pt(9)
            if r_idx == 0 or (c_idx > 0 and r_idx == c_idx):
                run.font.bold = True
            if r_idx == 0:
                set_cell_background(cell, "EAEAEA")
            set_cell_margins(cell, top=60, bottom=60, left=80, right=80)
    
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    add_subheading("Ablation Study: Criticality of the Spectral Branch")
    add_body_p(
        "To quantify the specific contribution of individual model components, an extensive ablation study was executed."
    )

    # Table 4
    p_t4_lbl = doc.add_paragraph()
    p_t4_lbl.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_t4_lbl = p_t4_lbl.add_run("Table 4. Ablation Study on Architectural Components")
    r_t4_lbl.font.name = "Cambria"
    r_t4_lbl.font.size = Pt(10)
    r_t4_lbl.font.bold = True
    p_t4_lbl.paragraph_format.space_after = Pt(2)

    table4_data = [
        ["Model Architecture Configuration", "Overall Accuracy", "Normal", "Inner", "Ball", "Outer"],
        ["ExtensiveCNN (Full: Temporal + Spectral)", "100.0%", "1.000", "1.000", "1.000", "1.000"],
        ["Without Spectral Branch (Temporal Only)", "80.4%", "1.000", "1.000", "1.000", "0.000"],
        ["Without Squeeze-and-Excitation (SE)", "96.8%", "1.000", "0.945", "0.962", "0.970"],
        ["Without Mixup Augmentation", "98.1%", "1.000", "0.975", "0.981", "0.972"],
        ["Traditional Statistical Classifier (Kurtosis)", "89.4%", "0.980", "0.840", "0.810", "0.930"]
    ]
    t4 = doc.add_table(rows=len(table4_data), cols=6)
    t4.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r_idx, row in enumerate(table4_data):
        for c_idx, val in enumerate(row):
            cell = t4.cell(r_idx, c_idx)
            cell.text = val
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if c_idx > 0 else WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            run = p.runs[0]
            run.font.name = "Times New Roman"
            run.font.size = Pt(9)
            if r_idx == 0 or r_idx == 1:
                run.font.bold = True
                if r_idx == 0:
                    set_cell_background(cell, "EAEAEA")
            set_cell_margins(cell, top=60, bottom=60, left=60, right=60)
    
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    add_body_p(
        "As detailed in Table 4, removing the spectral branch causes complete classification breakdown for Outer Race defects (0.0% recall). Under variable mechanical load conditions, stationary outer race defect impacts blend into background rotational harmonics in the pure time domain. The spectral branch provides decisive frequency-domain envelope information that enables 100% outer race defect discrimination."
    )

    add_subheading("System Latency, Resource and Power Benchmarking")
    add_body_p("Table 5 outlines the measured operational benchmarks across both hardware states.")

    # Table 5
    p_t5_lbl = doc.add_paragraph()
    p_t5_lbl.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_t5_lbl = p_t5_lbl.add_run("Table 5. Embedded System and Edge-Backend Operational Benchmarks")
    r_t5_lbl.font.name = "Cambria"
    r_t5_lbl.font.size = Pt(10)
    r_t5_lbl.font.bold = True
    p_t5_lbl.paragraph_format.space_after = Pt(2)

    table5_data = [
        ["Performance Metric", "Experimental Value", "Testing Condition / Hardware"],
        ["Dual-Mode Transition Latency", "12.4 ms", "Hardware button ISR to display buffer swap"],
        ["ExtensiveCNN Inference Time (GPU)", "3.2 ms", "NVIDIA GeForce RTX 3060 CUDA 12.4"],
        ["ExtensiveCNN Inference Time (CPU)", "21.6 ms", "Intel Core i7-13700H CPU"],
        ["ADXL345 100-Sample Burst Capture", "2.48 s", "40 Hz acquisition mode on ESP32-S3"],
        ["Full Inspection Roundtrip (Capture -> RUL)", "2.52 s", "Hardware capture + UART transfer + GPU inference"],
        ["ESP32-S3 SRAM Utilization", "142 KB / 512 KB (27.7%)", "Dual framebuffers + I2S DMA buffers"],
        ["ESP32-S3 Flash Utilization", "1.84 MB / 16.0 MB (11.5%)", "U8g2 fonts, FreeRTOS kernel, graphics routines"],
        ["Companion Mode Current Draw", "168 mA @ 3.7 V (0.62 W)", "Both screens on, LED ring active, Wi-Fi idle"],
        ["Inspection Mode Current Draw", "194 mA @ 3.7 V (0.72 W)", "Accelerometer active, TFT updating"],
        ["Battery Life (2500 mAh Li-Ion)", "≈ 12.8 hours", "Continuous mixed-mode operational cycle"]
    ]
    t5 = doc.add_table(rows=len(table5_data), cols=3)
    t5.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r_idx, row in enumerate(table5_data):
        for c_idx, val in enumerate(row):
            cell = t5.cell(r_idx, c_idx)
            cell.text = val
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if c_idx == 1 else WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            run = p.runs[0]
            run.font.name = "Times New Roman"
            run.font.size = Pt(9)
            if r_idx == 0:
                run.font.bold = True
                set_cell_background(cell, "EAEAEA")
            set_cell_margins(cell, top=60, bottom=60, left=80, right=80)
    
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    # V. CONCLUSION
    add_section_heading("V.   CONCLUSION")
    add_body_p(
        "This paper introduced OmniDesk, a converged cyber-physical edge system unifying an ambient desktop companion with an on-demand industrial vibration inspection and RUL prognostics instrument on a single ESP32-S3 hardware node. The dual-personality state machine enables zero-reboot switching between workspace assistance and machinery diagnostics in 12.4 ms."
    )
    add_body_p(
        "The diagnostic pipeline developed ExtensiveCNN, a deep dual-branch residual network incorporating Squeeze-and-Excitation attention, dilated convolutions, and a spectral FFT branch. Evaluated across 40 CWRU recordings using a strict recording-level split, the model attained 100.0% test accuracy on 2,420 test windows from held-out 3 hp recordings. Ablation experiments demonstrated that the spectral branch is vital for separating Outer Race defects under variable load, boosting recall from 0% to 100%. Concurrently, a physics-informed prognostics engine combined exponential degradation, linear regression, and Paris' law crack growth with ISO 10816-3 criteria to provide conservative RUL forecasts with residual confidence intervals. Meanwhile, the companion mode delivered procedural OLED facial animations, PC performance monitoring, and responsive voice interaction via NVIDIA Nemotron and a MAX98357A I2S audio subsystem."
    )
    add_body_p(
        "Future work includes on-device TinyML INT8 quantization via ESP-NN for fully untethered operation, integration of thermal imaging micro-sensors for localized friction mapping, and multi-node fleet mesh networking."
    )

    # ACKNOWLEDGEMENTS
    add_section_heading("ACKNOWLEDGEMENTS")
    add_body_p(
        "The authors express their sincere gratitude to the Department of Artificial Intelligence and Data Science at Dr. Akhilesh Das Gupta Institute of Professional Studies (ADGIPS), affiliated with Guru Gobind Singh Indraprastha University (GGSIPU), Delhi, India, for providing the institutional support, laboratory facilities, and computing infrastructure essential for completing this research."
    )

    # REFERENCES
    add_section_heading("REFERENCES")
    refs = [
        "S. Sharma, \"OmniDesk: Dual-Mode AI Industrial Inspection & Desk Companion,\" Product Requirements Document, Tech. Rep. PRD-2.0, Nov. 2026.",
        "Case Western Reserve University Bearing Data Center, \"Bearing Vibration Data Sets,\" Case Western Reserve University, Cleveland, OH, USA, Tech. Rep., 2002.",
        "ISO 10816-3:2009, Mechanical vibration — Evaluation of machine vibration by measurements on non-rotating parts — Part 3: Industrial machines with nominal power above 15 kW and nominal speeds between 120 r/min and 15 000 r/min, ISO, Geneva, Switzerland, 2009.",
        "P. Paris and F. Erdogan, \"A critical analysis of crack propagation laws,\" Journal of Basic Engineering, Vol. 85, Issue 4, Dec. 1963, pp. 528-533.",
        "K. He, X. Zhang, S. Ren, and J. Sun, \"Deep Residual Learning for Image Recognition,\" in Proc. IEEE Conf. on Computer Vision and Pattern Recognition (CVPR), 2016, pp. 770-778.",
        "J. Hu, L. Shen, and G. Sun, \"Squeeze-and-Excitation Networks,\" in Proc. IEEE Conf. on Computer Vision and Pattern Recognition (CVPR), 2018, pp. 7132-7141.",
        "H. Zhang, M. Cisse, Y. N. Dauphin, and D. Lopez-Paz, \"mixup: Beyond Empirical Risk Minimization,\" in Proc. Int. Conf. on Learning Representations (ICLR), 2018.",
        "O. Abdeljaber, O. Avci, S. Kiranyaz, M. Gabbouj, and D. J. Inman, \"Real-time vibration-based structural damage detection using one-dimensional convolutional neural networks,\" Journal of Sound and Vibration, Vol. 388, Feb. 2017, pp. 154-170.",
        "W. Zhang, G. Peng, C. Li, Y. Chen, and Z. Zhang, \"A new deep learning model for fault diagnosis with good anti-noise and domain adaptation ability on raw vibration signals,\" IEEE Transactions on Instrumentation and Measurement, Vol. 67, Issue 11, Nov. 2018, pp. 2542-2553.",
        "L. Eren, T. Ince, and S. Kiranyaz, \"A generic intelligent bearing fault diagnosis system using compact 1D CNN classifier,\" Journal of Signal Processing Systems, Vol. 91, Issue 2, Feb. 2019, pp. 179-189.",
        "R. Liu, B. Yang, E. Zio, and X. Chen, \"Artificial intelligence for fault diagnosis of rotating machinery: A review,\" Mechanical Systems and Signal Processing, Vol. 108, Aug. 2018, pp. 33-47.",
        "Y. Lei, N. Li, L. Guo, N. Li, T. Yan, and J. Lin, \"Machinery health prognostics: A systematic review from data acquisition to RUL prediction,\" Mechanical Systems and Signal Processing, Vol. 104, May 2018, pp. 799-834.",
        "X. Li, W. Zhang, and Q. Ding, \"Deep learning-based remaining useful life estimation of bearings using multi-scale feature extraction,\" IEEE Transactions on Reliability, Vol. 69, Issue 2, Jun. 2020, pp. 714-725.",
        "S. Kiranyaz, O. Avci, O. Abdeljaber, T. Ince, M. Gabbouj, and D. J. Inman, \"1D convolutional neural networks and applications: A survey,\" Mechanical Systems and Signal Processing, Vol. 151, Apr. 2021, p. 107398.",
        "P. K. Kankar, S. C. Sharma, and S. P. Harsha, \"Fault diagnosis of ball bearings using continuous wavelet transform and self organizing maps,\" Expert Systems with Applications, Vol. 38, Issue 8, Aug. 2011, pp. 10377-10386.",
        "H. Shao, H. Jiang, F. Wang, and Y. Zhao, \"An enhancement deep feature learning method for rotating machinery fault diagnosis,\" IEEE Transactions on Industrial Informatics, Vol. 13, Issue 2, Apr. 2017, pp. 750-758.",
        "D. T. Hoang and H. J. Kang, \"A survey on deep learning based bearing fault diagnosis,\" Neurocomputing, Vol. 335, Mar. 2019, pp. 327-335.",
        "S. Khan and T. Yairi, \"A review on the application of deep learning in system health management,\" Mechanical Systems and Signal Processing, Vol. 107, Jul. 2018, pp. 241-265.",
        "A. K. S. Jardine, D. Lin, and D. Banjevic, \"A review on machinery diagnostics and prognostics implementing condition-based maintenance,\" Mechanical Systems and Signal Processing, Vol. 20, Issue 7, Oct. 2006, pp. 1483-1510.",
        "C. Breazeal, Designing Sociable Robots, Cambridge, MA, USA: MIT Press, 2004.",
        "Espressif Systems, ESP32-S3 Series Technical Reference Manual, Version 1.4, Espressif Systems, Shanghai, China, 2023.",
        "Analog Devices, ADXL345: 3-Axis Digital Accelerometer Data Sheet, Rev. E, Analog Devices, Norwood, MA, USA, 2015.",
        "Bosch Sensortec, BME280 Combined humidity and pressure sensor Data sheet, Doc. Rev. 1.8, Bosch Sensortec GmbH, Reutlingen, Germany, 2021.",
        "A. Paszke et al., \"PyTorch: An imperative style, high-performance deep learning library,\" in Advances in Neural Information Processing Systems (NeurIPS 32), 2019, pp. 8024-8035.",
        "NVIDIA Corporation, NVIDIA Nemotron-3 Architecture and Implementation, NVIDIA Technical Whitepaper, Santa Clara, CA, USA, 2024.",
        "J. Lee, F. Wu, W. Zhao, M. Ghaffari, L. Liao, and D. Siegel, \"Prognostics and health management design for rotary machinery systems,\" Industrial Management & Data Systems, Vol. 114, Issue 7, Aug. 2014, pp. 992-1010.",
        "M. Cerrada et al., \"A review on data-driven fault severity assessment in rolling bearings,\" Mechanical Systems and Signal Processing, Vol. 99, Jan. 2018, pp. 169-196.",
        "F. Tiuraniemi et al., \"User experience of expressive physical social desktop agents: An empirical evaluation,\" in Proc. ACM/IEEE Int. Conf. Human-Robot Interaction (HRI), 2022, pp. 312-320."
    ]

    for idx, ref in enumerate(refs, 1):
        p_ref = doc.add_paragraph()
        p_ref.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p_ref.paragraph_format.space_after = Pt(3)
        p_ref.paragraph_format.line_spacing = 1.15
        r_num = p_ref.add_run(f"[{idx}] ")
        r_num.font.name = "Times New Roman"
        r_num.font.size = Pt(10)
        r_num.font.bold = True
        r_txt = p_ref.add_run(ref)
        r_txt.font.name = "Times New Roman"
        r_txt.font.size = Pt(10)

    doc.save(output_path)
    print("SUCCESS: Created", output_path)

if __name__ == "__main__":
    create_document()
