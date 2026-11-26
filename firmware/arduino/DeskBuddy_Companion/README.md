# Omnipect Companion Firmware

Arduino IDE sketch for the ESP32-S3 Omnipect. It renders an expressive OLED
face, a multi-page ST7735 dashboard, and talks to `deskbuddy_backend` over a
newline-delimited JSON serial link at 115200 baud.

This folder is intentionally separate from the old PlatformIO experiments in
`firmware/`. Flash this sketch from the Arduino IDE.

## Hardware

| Device | Signal | ESP32-S3 pin |
|---|---|---|
| SH1106 OLED 128x64 | SDA | GPIO8 |
| SH1106 OLED 128x64 | SCL | GPIO9 |
| BME280 | SDA / SCL | GPIO8 / GPIO9 |
| ADXL345 | SDA / SCL | GPIO8 / GPIO9 |
| ST7735 TFT | CS | GPIO10 |
| ST7735 TFT | MOSI | GPIO11 |
| ST7735 TFT | SCLK | GPIO12 |
| ST7735 TFT | DC | GPIO13 |
| ST7735 TFT | RST | GPIO14 |
| ST7735 TFT | BL | GPIO15 |
| MODE button | to GND | GPIO16 |
| VOICE button | to GND | GPIO17 |
| UP button | to GND | GPIO19 |
| DOWN button | to GND | GPIO18 |
| SELECT button | to GND | GPIO4 |
| Speaker / buzzer | PWM | GPIO21 |
| Battery sense | divider | GPIO1 (ADC1, see note below) |
| I2S mic (INMP441 / ICS-43434) | SCK / BCLK | GPIO5 |
| I2S mic | WS / LRCLK | GPIO6 |
| I2S mic | SD / DOUT | GPIO7 |
| Addressable LED strip (optional, 16 LEDs) | Data | GPIO48 (alt GPIO2) |

I2C addresses: OLED `0x3C`, BME280 `0x77` (with `0x76` fallback), ADXL345
`0x53`. Buttons use `INPUT_PULLUP` and are active LOW. The I2S mic runs at
16 kHz, 32-bit mono slots; tie its `L/R` pin to GND (left channel) and power it
from 3.3 V.

> **N16R8 pin warning:** GPIO26-GPIO32 are used by the in-package SPI flash,
> and GPIO33-GPIO37 are not available on the ESP32-S3-WROOM-1 module (octal
> PSRAM variants). Do not connect anything to those pins and do not configure
> them in software. The original map used DOWN=GPIO32, speaker=GPIO33, and
> battery=GPIO34; those are invalid on this module and caused a boot-time panic.
> The firmware now uses DOWN=GPIO18, speaker=GPIO21, and battery=GPIO1. Move
> those three wires if your board was wired to the old pins.
>
> **Battery pin note:** on the ESP32-S3, ADC1 is available on GPIO1-GPIO10
> (ADC2 on GPIO11-GPIO20). GPIO1 is ADC1_CH0, so a divider on GPIO1 works. If
> the divider is still on GPIO34, move it to GPIO1 for a local reading. The
> firmware still accepts the battery percentage from the backend (`batt`), so
> the UI can show a value when the ADC is unavailable.

## Arduino IDE settings

- Board: **ESP32S3 Dev Module**
- Flash Size: **16MB**
- Flash Mode: **QIO 80MHz**
- PSRAM: **OPI PSRAM**
- Partition Scheme: **16M Flash (3MB APP/9.9MB FATFS)**
- USB CDC On Boot: **Disabled** (the backend uses the UART/USB serial port that
  appears as `COMx`; enable this only if your board exposes a native USB CDC
  port and you have changed the backend port accordingly)
- Upload Speed: 921600 (drop to 460800 or 115200 if uploads fail)

## Libraries

Install these through **Tools > Manage Libraries**:

- U8g2
- Adafruit GFX Library
- Adafruit ST7735 and ST7789 Library
- Adafruit BME280 Library
- Adafruit Unified Sensor
- Adafruit ADXL345
- ArduinoJson (v7)

The I2S microphone uses the `ESP_I2S` library bundled with the ESP32 Arduino
core 3.x, so no separate library install is needed. The sketch compiles with
ESP32 Arduino core `3.3.13`.

## Backend link

Start the backend from `deskbuddy_backend`:

```powershell
C:\Users\Suryansh3584\.conda\envs\inspection\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Set the serial port in `deskbuddy_backend/.env`, for example:

```dotenv
SERIAL_PORT=COM6
SERIAL_BAUD=115200
ENABLE_COMPANION=true
```

Close the Arduino IDE Serial Monitor before starting the backend. Only one
process can own a COM port on Windows; a busy port produces
`PermissionError(13, 'Access is denied.')`.

The backend pushes a compact state packet every second:

```json
{"cmd":"deskbuddy_state","payload":{
  "act":"coding","expr":"coding","sleep":"active",
  "app":"Code.exe","win":"companion.py - Visual Studio Code",
  "idle":0,"audio":0,"cpu":12.4,"mem":48.1,"gpu":3.0,"ctemp":51.0,
  "tz":17.0,"gtemp":48.0,"gmem":7.2,"gvram":12288,"gfan":66.0,
  "m_title":"Blinding Lights","m_artist":"The Weeknd","m_play":1,
  "m_prog":42,"m_dur":200,
  "lyr_ok":1,"lyr_sync":1,"lyr_idx":10,"lyr_tot":35,
  "lyr_prev":"No one's around to judge me",
  "lyr_cur":"I can't see clearly when you're gone",
  "lyr_next":"I said, Ooh, I'm blinded by the lights",
  "pomo_run":0,"pomo_rem":0,"pomo_break":0,
  "env_t":24.5,"env_h":51.0,"env_p":1013.0,
  "batt":72,"batt_v":11.8,"batt_chg":-1,"mic":34,
  "unread":0,"clock":"14:05","date":"2026-11-19","dow":"Thu",
  "epoch":1763553900,"dev_online":1,"mode":"desk_buddy","page":"home"
}}
```

`batt` is the battery percentage (or `-1` when unknown), `batt_v` is the pack
voltage, and `batt_chg` is `-1` because the known-good wiring has no
charge-detect pin. `mic` is a 0-100 input level, or `-1` when no I2S mic is
detected. `ctemp` is the real CPU temperature when `psutil`, LibreHardwareMonitor,
or OpenHardwareMonitor can supply it; `tz` is the separate ACPI thermal-zone
reading (usually ambient). GPU fields are populated through NVML with an
`nvidia-smi` fallback.

The firmware also accepts these commands:

| Command | Payload | Effect |
|---|---|---|
| `notification` | `{"title":"...","message":"...","priority":2,"id":"..."}` | Adds a notification, shows the notification page, beeps |
| `pomodoro` | `{"action":"start","minutes":25}` / `pause` / `reset` | Controls the local Pomodoro timer |
| `music` | `{"action":"play"}` or `pause` | Updates the music page state |
| `mode_switch` | `{"mode":"inspection"}` or `desk_buddy` | Switches the TFT mode |
| `page` | `{"page":0..6}` | Jumps to a dashboard page |
| `brightness` | `{"level":0..255}` | Sets TFT backlight |
| `play_tone` | `{"frequency":1200,"duration":100}` | Beeps the speaker |

The device sends these message types back to the backend:

- `heartbeat` every 5 s: firmware, page, mode, expression, uptime, heap,
  battery, BME280/ADXL345/mic status
- `sensor_data` every 2 s: temperature, humidity, pressure, accelerometer,
  battery voltage/percentage, mic level
- `button` on every button press: `mode`, `voice`, `up`, `down`, `select`
- `gesture`: `single_tap`, `double_tap`, `triple_tap`, or `shake`
- `music` for play/pause requests
- `pomodoro` for start/pause requests
- `notification_ack` when a notification is marked read
- `mode_switched` when the MODE button changes the device mode

## Buttons

| Button | Normal behavior |
|---|---|
| MODE | Toggle DeskBuddy / Inspection mode |
| VOICE | Wake the face and send a voice request to the backend |
| UP | Previous dashboard page |
| DOWN | Next dashboard page |
| SELECT | Page action: play/pause music, start/pause Pomodoro, mark a notification read, or advance the page |

Pages cycle HOME -> MUSIC -> LYRICS -> PC -> ENV -> NOTIFICATIONS -> POMODORO.
On the MUSIC and LYRICS pages, SELECT toggles play/pause.

## Face behavior and gestures

- Pupils follow the ADXL345 tilt.
- Blinks happen every 2.5 to 5.5 seconds.
- Single tap wakes the face (`single_tap`).
- Double tap wakes and opens the MUSIC page (`double_tap`).
- Triple tap wakes and sends a voice request (`triple_tap`).
- A shake wakes the face, returns to HOME, and shows a surprised expression
  (`shake`).
- The backend expression drives the face: `coding`, `browsing`, `music`,
  `gaming`, `watching`, `typing`, `thinking`, `happy`, `sad`, `angry`,
  `sleepy`, `curious`, `excited`, `surprised`, `confused`, `laughing`,
  `sleeping`, `deep_sleep`.
- If no backend state arrives for 15 seconds, the device enters autonomous mode
  and cycles gentle expressions on its own.
- Sleep stages dim the TFT and OLED. `deep_sleep` turns the TFT backlight off
  and shows a dim `Z z z` on the OLED. Motion or a button press wakes it.

## Lyrics screen

The LYRICS page shows the previous, current, and next line for the track the
backend is playing. The backend looks tracks up on [LRCLIB](https://lrclib.net)
by title, artist, and duration, then sends three compact lines plus a
`SYNCED`/`UNSYNCED` badge. Unsynced lyrics stay static instead of pretending to
scroll. Lookups are cached per track, so the 1 Hz state push does not generate
network traffic.

The full cached sheet is available to web dashboards at:

```text
GET /api/v1/desktop/music/lyrics/full
```

## Battery and microphone

The firmware smooths the battery ADC and maps a 3S Li-ion pack through a
piecewise discharge curve (12.6 V = 100 %, 9.0 V = 0 %). A divider reading in
the 4-5.5 V range is treated as USB power. Charging state is reported as
unknown because there is no charge-detect pin.

The I2S microphone computes an RMS level about 50 times per second and maps
it from dBFS to 0-100. The level appears on the ENVIRONMENT page and in
`sensor_data.mic_level`; the backend forwards it as `mic` in the device state.
Tie the INMP441 `L/R` pin to GND and use 3.3 V power. If the mic is absent or
I2S initialization fails, the firmware reports `mic: -1` and the dashboard says
`offline`.

## Troubleshooting

**Upload fails with "port busy"** — close the Arduino Serial Monitor, the
backend, and any other serial terminal. Check with:

```powershell
Get-Process | Where-Object { $_.ProcessName -match 'arduino|python' }
Get-PnpDevice -Class Ports | Where-Object { $_.FriendlyName -match 'COM' }
```

If the CH343/CP210x entry shows `Status: Unknown`, Windows does not currently
see the board (check the USB cable, boot mode, and driver). `POST
/api/v1/device/connect` cannot open a port that is not enumerated.

**OLED stays blank** — confirm the SH1106 address is `0x3C` and that SDA/SCL
are GPIO8/GPIO9. A 100 kHz I2C clock is used for reliability.

**TFT colors are inverted or offset** — the sketch uses `INITR_BLACKTAB`.
Some 1.8" modules need `INITR_GREENTAB` or `INITR_REDTAB`; change the
`tft.initR(...)` line in `initTft()` if the image is shifted.

**Battery reading is wrong** — the sketch assumes a 3S pack and an 11:1
divider. Adjust `BATTERY_DIVIDER` for your divider and edit the
`BATTERY_CURVE` table for a different chemistry or cell count. The divider
must be on an ADC1 pin; the sketch uses GPIO1. If it is still on GPIO34, move
it to GPIO1.

**Board reboots in a loop / TG1WDT_SYS_RST** — do not use GPIO26-GPIO32
(internal flash) or GPIO33-GPIO37 (unavailable on the octal-PSRAM WROOM-1
module). Check that DOWN is on GPIO18, speaker on GPIO21, and battery on
GPIO1.

**Battery shows NO BATTERY** — this is expected when the ADC pin is not
connected or is on a non-ADC GPIO. The TFT still uses the backend's `batt`
percentage when one is available.

**No serial state** — verify the backend is connected to the same COM port and
that `ENABLE_COMPANION=true`. The firmware sends a `status` packet at boot and
a `heartbeat` every 5 seconds, so the backend should report the device online
even before the first state push.
