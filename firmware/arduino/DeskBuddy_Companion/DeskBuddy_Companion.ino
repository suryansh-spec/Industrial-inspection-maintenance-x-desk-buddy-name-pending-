// ============================================================================
// DeskBuddy Companion - Arduino IDE sketch
// ============================================================================
// A PC-aware desk companion for the ESP32-S3 N16R8.
//
// Inspired by:
//   * DeskMate       - expressive, low-distraction desk device
//   * deskey-v2      - PC activity, heartbeat, sleep engine, autonomous mode
//   * StatNode       - compact PC metrics dashboard
//   * yt-music       - now-playing screen and media controls
//   * Hermes         - push-to-talk voice button
//
// The PC backend (deskbuddy_backend) does the heavy lifting: foreground app
// detection, idle time, music metadata, PC metrics and voice. This sketch owns
// the immediate device experience so the face stays alive even when the PC
// link drops.
//
// Hardware (known-good wiring)
//   ESP32-S3 N16R8, Arduino IDE board: "ESP32S3 Dev Module"
//     Flash Size 16MB, Flash Mode QIO, 80MHz, PSRAM OPI PSRAM,
//     Partition 16M Flash (3MB APP/9.9MB FATFS), USB CDC On Boot Disabled
//
//   I2C  SDA=GPIO8, SCL=GPIO9, 100kHz
//     SH1106 OLED 128x64 @ 0x3C
//     BME280 @ 0x77 (0x76 fallback)
//     ADXL345 @ 0x53
//
//   SPI ST7735 TFT
//     CS=10, MOSI=11, SCLK=12, DC=13, RST=14, BL=15
//
//   Buttons (INPUT_PULLUP, active LOW)
//     MODE=16, VOICE=17, UP=19, DOWN=18, SELECT=4
//   Speaker PWM=21, battery ADC=1
//
// Libraries (Arduino Library Manager)
//   U8g2
//   Adafruit GFX Library
//   Adafruit ST7735 and ST7789 Library
//   Adafruit BME280 Library + Adafruit Unified Sensor
//   Adafruit ADXL345
//   ArduinoJson (v7)
//
// Serial protocol (115200 baud, newline-delimited JSON)
//   PC -> device:
//     {"cmd":"deskbuddy_state","payload":{ "act":"coding", ... }}
//     {"cmd":"notification","payload":{ "title":"...", "message":"..." }}
//     {"cmd":"pomodoro","payload":{ "action":"start", "minutes":25 }}
//     {"cmd":"music","payload":{ "action":"pause" }}
//     {"cmd":"mode_switch","payload":{ "mode":"inspection" }}
//     {"cmd":"page","payload":{ "page":2 }}
//     {"cmd":"brightness","payload":{ "level":128 }}
//   device -> PC:
//     {"type":"heartbeat",...}
//     {"type":"sensor_data",...}
//     {"type":"button","button":"select","page":"music"}
//     {"type":"gesture","gesture":"double_tap","page":"music"}
//     {"type":"music","action":"play"}
//     {"type":"pomodoro","action":"start","minutes":25}
//     {"type":"notification_ack","id":"..."}
//     {"type":"mode_switched","mode":"inspection"}
// ============================================================================

#include <Arduino.h>
#include <Wire.h>
#include <SPI.h>
#include "driver/gpio.h"
#include <U8g2lib.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <Adafruit_BME280.h>
#include <Adafruit_ADXL345_U.h>
#include <ESP_I2S.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <math.h>

// Optional compile-time voice/Wi-Fi configuration. Create voice_config.h next
// to this sketch (see voice_config.example.h). Values sent over serial are
// stored in NVS and take precedence over these defaults.
#if __has_include("voice_config.h")
#include "voice_config.h"
#endif

#if __has_include(<U8g2_for_Adafruit_GFX.h>)
#include <U8g2_for_Adafruit_GFX.h>
#define HAS_U8G2_GFX 1
#endif

// Optional addressable LED strip support (WS2812B/NeoPixel).
// Auto-enables when Adafruit NeoPixel library is installed. To force off,
// define LED_STRIP_DISABLED before this block (or do not install the lib).
// Addressable LED strip support (WS2812B/NeoPixel). Enabled by default.
// Requires the Adafruit NeoPixel library. To disable, define LED_STRIP_DISABLED.
#ifndef LED_STRIP_DISABLED
#define ENABLE_LED_STRIP 1
#endif

#if defined(ENABLE_LED_STRIP)
#include <Adafruit_NeoPixel.h>
#include "led_strip.h"
#endif

// ----------------------------------------------------------------------------
// Pin map
// ----------------------------------------------------------------------------
#define PIN_I2C_SDA       8
#define PIN_I2C_SCL       9

#define PIN_TFT_CS        10
#define PIN_TFT_MOSI      11
#define PIN_TFT_SCLK      12
#define PIN_TFT_DC        13
#define PIN_TFT_RST       14
#define PIN_TFT_BL        15

#define PIN_BTN_MODE      16
#define PIN_BTN_VOICE     17
#define PIN_BTN_UP        19
#define PIN_BTN_DOWN      18
#define PIN_BTN_SELECT    4

#define PIN_SPEAKER       -1  // Disabled: GPIO 21 is used by the NeoPixel LED ring
#define PIN_BATTERY       1

// MAX98357A I2S voice output (optional; the base build still uses the PWM
// speaker on GPIO21 for beeps). These pins are free on the ESP32-S3 DevKitC-1.
#define PIN_AMP_BCLK      40
#define PIN_AMP_LRC       41
#define PIN_AMP_DIN       42

// I2S MEMS microphone (INMP441 / ICS-43434). Tie the mic's L/R pin to GND so
// it drives the left slot; the firmware reads mono 32-bit slots.

// Device theme (colors in RGB565)
struct DeviceTheme {
  uint16_t bg;
  uint16_t text;
  uint16_t accent;
  uint16_t secondary;
  uint16_t warning;
  uint16_t success;
  uint16_t danger;
  uint16_t headerBg;
  uint16_t headerText;
  uint8_t titleSize;
  uint8_t bodySize;
  uint8_t bigSize;
  uint8_t timerSize;
};

DeviceTheme theme = {
  0x0000,  // bg (black)
  0xFFFF,  // text (white)
  0x07FF,  // accent (cyan)
  0x8410,  // secondary (gray)
  0xFD20,  // warning (orange)
  0x07E0,  // success (green)
  0xF800,  // danger (red)
  0x0010,  // headerBg (dark blue)
  0xFFFF,  // headerText (white)
  2,       // titleSize
  1,       // bodySize
  3,       // bigSize
  4        // timerSize
};

// Convert hex color string to RGB565.
// Accepts 3 (#RGB), 4 (#RGB565), 6 (#RRGGBB) or 8 (#RRGGBBAA) digit forms.
// Parsing is done manually (no strtoul) so it works regardless of libc.
uint16_t hexToRgb565(const char* hex) {
  if (hex == nullptr || hex[0] != '#') return 0x0000;
  int len = 0;
  while (hex[1 + len] != '\0' && len < 8) len++;
  if (len != 3 && len != 4 && len != 6 && len != 8) return 0x0000;

  unsigned long val = 0;
  for (int i = 0; i < len; i++) {
    char c = hex[1 + i];
    int digit;
    if (c >= '0' && c <= '9') digit = c - '0';
    else if (c >= 'a' && c <= 'f') digit = c - 'a' + 10;
    else if (c >= 'A' && c <= 'F') digit = c - 'A' + 10;
    else return 0x0000;
    val = (val << 4) | (unsigned long)digit;
  }

  // 4 hex digits are already RGB565.
  if (len == 4) {
    return (uint16_t)val;
  }

  uint8_t r, g, b;
  if (len == 3) {
    r = (uint8_t)(((val >> 8) & 0xF) * 17);
    g = (uint8_t)(((val >> 4) & 0xF) * 17);
    b = (uint8_t)((val & 0xF) * 17);
  } else if (len == 6) {
    r = (uint8_t)((val >> 16) & 0xFF);
    g = (uint8_t)((val >> 8) & 0xFF);
    b = (uint8_t)(val & 0xFF);
  } else { // len == 8, ignore alpha
    r = (uint8_t)((val >> 24) & 0xFF);
    g = (uint8_t)((val >> 16) & 0xFF);
    b = (uint8_t)((val >> 8) & 0xFF);
  }
  return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
}

// Inspection capture buffer (1200 samples at ~40 Hz = 30 seconds)
#define INSPECT_SAMPLES 100
float inspectX[INSPECT_SAMPLES];
float inspectY[INSPECT_SAMPLES];
float inspectZ[INSPECT_SAMPLES];
int inspectCount = 0;
bool inspectCapturing = false;
unsigned long inspectStartMs = 0;
bool inspectResultReady = false;
char inspectResultClass[24] = "";
float inspectResultConf = 0.0f;
char inspectResultAxis[8] = "";
#define PIN_MIC_SCK       5
#define PIN_MIC_WS        6
#define PIN_MIC_SD        7

// Battery divider: 3S pack, 11:1 resistor divider (same as the old sketch).
#define BATTERY_DIVIDER   11.0f
#define BATTERY_MIN_V     9.0f
#define BATTERY_MAX_V     12.6f

// ----------------------------------------------------------------------------
// Timing
// ----------------------------------------------------------------------------
const unsigned long MOTION_MS        = 25;    // ADXL345 sampling for gestures
const unsigned long ENV_MS           = 2000;  // BME280 is slow; no need to rush
const unsigned long BATTERY_MS       = 1000;
const unsigned long MIC_MS           = 20;    // 16 kHz / 320 samples per tick
const unsigned long BUTTON_MS        = 20;
const unsigned long POMODORO_MS      = 1000;
const unsigned long EYE_FRAME_MS     = 100;   // ~10 fps on a 100 kHz I2C bus
const unsigned long TFT_REFRESH_MS   = 33;
const unsigned long HEARTBEAT_MS     = 5000;
const unsigned long SENSOR_SEND_MS   = 2000;
const unsigned long STATE_TIMEOUT_MS = 15000;
const unsigned long NOTICE_HOLD_MS   = 6000;

#define FW_VERSION "2.0.0"
#define POMODORO_WORK_SECONDS   (25 * 60)
#define POMODORO_SHORT_SECONDS  (5 * 60)
#define POMODORO_LONG_SECONDS   (15 * 60)

// ----------------------------------------------------------------------------
// Displays
// ----------------------------------------------------------------------------
U8G2_SH1106_128X64_NONAME_F_HW_I2C oled(
    U8G2_R2, U8X8_PIN_NONE, PIN_I2C_SCL, PIN_I2C_SDA);

Adafruit_ST7735 tft(PIN_TFT_CS, PIN_TFT_DC, PIN_TFT_RST);
Adafruit_BME280 bme;
Adafruit_ADXL345_Unified adxl(12345);

// ----------------------------------------------------------------------------
// State vocabulary
// ----------------------------------------------------------------------------
enum DeviceMode {
  MODE_OMNIPECT,
  MODE_INSPECTION,
  MODE_DESK_BUDDY = MODE_OMNIPECT
};

enum ScreenPage {
  PAGE_HOME,
  PAGE_MUSIC,
  PAGE_LYRICS,
  PAGE_PC,
  PAGE_ENV,
  PAGE_NOTIFICATIONS,
  PAGE_POMODORO,
  PAGE_FONT_TEST,
  PAGE_COUNT
};

enum EyeExpression {
  EXPR_RELAXED,
  EXPR_HAPPY,
  EXPR_SAD,
  EXPR_ANGRY,
  EXPR_SLEEPY,
  EXPR_THINKING,
  EXPR_CURIOUS,
  EXPR_EXCITED,
  EXPR_SURPRISED,
  EXPR_CONFUSED,
  EXPR_LAUGHING,
  EXPR_MUSIC,
  EXPR_TYPING,
  EXPR_CODING,
  EXPR_BROWSING,
  EXPR_GAMING,
  EXPR_WATCHING,
  EXPR_SLEEPING,
  EXPR_DEEP_SLEEP,
  EXPR_AUTONOMOUS,
  EXPR_TALKING,   // Voice agent active — animated waveform mouth
  EXPR_ALARMED,   // Fault detected — wide eyes + alert frame
  EXPR_COUNT
};

// ----------------------------------------------------------------------------
// Data structures
// ----------------------------------------------------------------------------
struct DeskState {
  char activity[20];
  char expression[24];
  char sleepStage[16];
  char appName[32];
  char windowTitle[72];
  int  idleSeconds;
  bool audioActive;

  float cpu;
  float mem;
  float gpu;
  float cpuTemp;
  float thermalZone;
  float gpuTemp;
  float gpuMem;
  int   gpuVramMb;
  float gpuFan;

  char musicTitle[64];
  char musicArtist[48];
  bool musicPlaying;
  int  musicProgress;
  int  musicDuration;

  char lyricPrev[128];
  char lyricCur[128];
  char lyricNext[128];
  bool lyricsAvailable;
  bool lyricsSynced;
  int  lyricIndex;
  int  lyricTotal;

  int  backendBatteryPct;
  int  backendBatteryChg;

  int  unread;
  char clockText[8];
  char dateText[16];
  char dowText[8];
  long epoch;

  bool backendOnline;
  bool stateReceived;
  unsigned long lastStateMs;
};

struct SensorState {
  float accelX;
  float accelY;
  float accelZ;
  float temperature;
  float humidity;
  float pressure;
  float batteryVoltage;
  int   micLevel;
  bool bmeOk;
  bool adxlOk;
  bool micOk;
};

struct PomodoroState {
  bool running;
  bool isBreak;
  int  remaining;
  int  session;
  unsigned long lastTick;
};

struct Note {
  char id[20];
  char title[48];
  char message[96];
  int  priority;
  bool read;
};

// ----------------------------------------------------------------------------
// Globals
// ----------------------------------------------------------------------------
DeskState state;
SensorState sensors;
I2SClass i2s;
int32_t micBuffer[320];
float micLevelSmoothed = 0.0f;

I2SClass audioOut;
bool audioOutReady = false;

void playI2STone(int frequency, int durationMs) {
  if (!audioOutReady || frequency <= 0 || durationMs <= 0) return;
  int totalSamples = (16000 * durationMs) / 1000;
  int16_t buffer[64];
  float phaseStep = 2.0f * 3.14159265f * (float)frequency / 16000.0f;
  float phase = 0.0f;
  int sent = 0;
  while (sent < totalSamples) {
    int batch = totalSamples - sent;
    if (batch > 64) batch = 64;
    for (int i = 0; i < batch; i++) {
      buffer[i] = (int16_t)(sinf(phase) * 14000.0f);
      phase += phaseStep;
      if (phase >= 6.2831853f) phase -= 6.2831853f;
    }
    audioOut.write((const uint8_t*)buffer, batch * sizeof(int16_t));
    sent += batch;
  }
}

void playStartupMelody() {
  playI2STone(523, 90);   // C5
  delay(15);
  playI2STone(659, 90);   // E5
  delay(15);
  playI2STone(784, 90);   // G5
  delay(15);
  playI2STone(1046, 220); // C6
}

// FFT visualizer state (256-point real FFT on mic samples)
#define FFT_N 256
#define FFT_BARS 16
float fftRe[FFT_N];
float fftIm[FFT_N];
float fftBins[FFT_BARS];
float fftBassAvg = 0.0f;
bool fftBeat = false;
unsigned long fftBeatMs = 0;
PomodoroState pomodoro;
Note notes[8];
int noteCount = 0;

DeviceMode mode = MODE_OMNIPECT;
ScreenPage page = PAGE_HOME;

EyeExpression currentExpr = EXPR_RELAXED;
EyeExpression targetExpr = EXPR_RELAXED;

unsigned long lastButtonMs = 0;
unsigned long lastPomodoroMs = 0;
unsigned long lastEyeMs = 0;
unsigned long lastTftMs = 0;
unsigned long lastHeartbeatMs = 0;
unsigned long lastSensorSendMs = 0;
unsigned long lastMotionReadMs = 0;
unsigned long lastEnvReadMs = 0;
unsigned long lastBatteryReadMs = 0;
unsigned long lastMicReadMs = 0;
unsigned long lastMotionMs = 0;
unsigned long nextBlinkMs = 0;
unsigned long blinkUntil = 0;
unsigned long wakeUntil = 0;
unsigned long nextAutonomousMs = 0;
unsigned long lastShakeMs = 0;
unsigned long noticeUntil = 0;
unsigned long tapWindowMs = 0;
unsigned long lastImpactMs = 0;
unsigned long gestureLockUntil = 0;
unsigned long shakeWindowMs = 0;

bool blinking = false;
bool tftDirty = true;
bool tftFullRedraw = true;

// Music page partial-refresh tracking
bool lastMusicPlaying = false;
int lastMusicPercent = -1;
float dispProgress = -1.0f;
float lastDispProgress = -1.0f;
char lastProgressText[24] = "";
char lastMusicTitle[64] = "";
bool noticeOverride = false;
bool serialBufferOverflow = false;
int  tapCount = 0;
int  shakeHits = 0;
int  lastBacklight = -1;

ScreenPage pageBeforeNotice = PAGE_HOME;

float pupilX = 0.0f;
float pupilY = 0.0f;
float targetPupilX = 0.0f;
float targetPupilY = 0.0f;

String serialBuffer;
JsonDocument rxDoc;
JsonDocument txDoc;

// ----------------------------------------------------------------------------
// Optional cloud link (WebSocket over TLS).
// Set CLOUD_WS_HOST (+ CLOUD_WS_TOKEN) in voice_config.h, set
// VOICE_WIFI_ALWAYS_ON to 1, and install the "WebSockets" library by Markus
// Sattler. Every JSON line sent over USB serial is mirrored to the cloud
// backend and every line received from the cloud is handled exactly like a
// line from the serial port. USB serial keeps working in parallel.
// ----------------------------------------------------------------------------
#ifndef CLOUD_WS_HOST
#define CLOUD_WS_HOST ""
#endif
#ifndef CLOUD_WS_PORT
#define CLOUD_WS_PORT 443
#endif
#ifndef CLOUD_WS_TOKEN
#define CLOUD_WS_TOKEN ""
#endif
#ifndef CLOUD_WS_PATH
#define CLOUD_WS_PATH "/ws/device"
#endif
#if __has_include(<WebSocketsClient.h>)
#include <WebSocketsClient.h>
#define CLOUD_WS_ENABLED 1
#else
#define CLOUD_WS_ENABLED 0
#endif

void handleBackendLine(const String& line);

#if CLOUD_WS_ENABLED
WebSocketsClient cloudWs;
bool cloudWsStarted = false;
bool cloudWsConnected = false;

void cloudWsEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      cloudWsConnected = true;
      Serial.println("[cloud] connected");
      break;
    case WStype_DISCONNECTED:
      if (cloudWsConnected) Serial.println("[cloud] disconnected");
      cloudWsConnected = false;
      break;
    case WStype_TEXT: {
      String line((const char*)payload, length);
      line.trim();
      if (line.length() > 0) handleBackendLine(line);
      break;
    }
    default:
      break;
  }
}

void cloudTick() {
  if (strlen(CLOUD_WS_HOST) == 0) return;
  if (WiFi.status() != WL_CONNECTED) {
    cloudWsConnected = false;
    return;
  }
  if (!cloudWsStarted) {
    String path = String(CLOUD_WS_PATH);
    if (strlen(CLOUD_WS_TOKEN) > 0) path += String("?token=") + CLOUD_WS_TOKEN;
    cloudWs.beginSSL(CLOUD_WS_HOST, CLOUD_WS_PORT, path.c_str());
    cloudWs.onEvent(cloudWsEvent);
    cloudWs.setReconnectInterval(3000);
    cloudWs.enableHeartbeat(15000, 4000, 2);
    cloudWsStarted = true;
    Serial.printf("[cloud] connecting to %s\n", CLOUD_WS_HOST);
  }
  cloudWs.loop();
}

void cloudSendLine(const String& s) {
  if (cloudWsConnected) cloudWs.sendTXT(s);
}
#else
void cloudTick() {}
void cloudSendLine(const String&) {}
#endif

// Send a JSON message to the backend over USB serial and the cloud link.
void sendTx(JsonDocument& doc) {
  String s;
  serializeJson(doc, s);
  Serial.println(s);
  cloudSendLine(s);
}

const int BUTTON_PINS[5] = {
  PIN_BTN_MODE, PIN_BTN_VOICE, PIN_BTN_UP, PIN_BTN_DOWN, PIN_BTN_SELECT
};
const char* BUTTON_NAMES[5] = {
  "mode", "voice", "up", "down", "select"
};
bool buttonStable[5] = {true, true, true, true, true};
bool buttonLastRead[5] = {true, true, true, true, true};
bool buttonPressed[5] = {false, false, false, false, false};
unsigned long buttonDebounceMs[5] = {0, 0, 0, 0, 0};

// ----------------------------------------------------------------------------
// Cover Art and Blurred Lyrics Background (PSRAM)
// ----------------------------------------------------------------------------
#define COVER_THUMB_W 40
#define COVER_THUMB_H 40
#define COVER_BG_SRC_W 32
#define COVER_BG_SRC_H 40
#define TFT_W 128
#define TFT_H 160

uint16_t* coverThumb = nullptr;      // 40x40 = 1600 uint16_t (3200 bytes)
uint16_t* lyricsBg = nullptr;        // 128x160 = 20480 uint16_t (40960 bytes)
bool hasCoverThumb = false;
bool hasLyricsBg = false;
char coverTrack[64] = "";

// Permanent wallpaper (set from the web panel). Streamed in chunks, kept in
// PSRAM and re-pushed by the backend on every connect.
#define WALLPAPER_CHUNK 1536
uint16_t* wallpaperBuf = nullptr;    // 128x160 RGB565, little-endian
bool      hasWallpaper = false;
uint8_t   wallpaperOpacity = 150;    // scrim toward theme.bg (0..255)
uint32_t  wallpaperVersion = 0;
uint32_t  wallpaperRecv = 0;
uint32_t  wallpaperTotal = 0;

int decodeBase64(const char* input, uint8_t* output, int maxOut) {
  static const int8_t T[256] = {
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,62,-1,-1,-1,63,
    52,53,54,55,56,57,58,59,60,61,-1,-1,-1, 0,-1,-1,
    -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9,10,11,12,13,14,
    15,16,17,18,19,20,21,22,23,24,25,-1,-1,-1,-1,-1,
    -1,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,
    41,42,43,44,45,46,47,48,49,50,51,-1,-1,-1,-1,-1
  };
  int len = 0;
  uint32_t val = 0;
  int bits = -8;
  for (const char* p = input; *p && *p != '='; p++) {
    uint8_t c = (uint8_t)*p;
    if (c > 127 || T[c] == -1) continue;
    val = (val << 6) | T[c];
    bits += 6;
    if (bits >= 0) {
      if (len < maxOut) output[len++] = (uint8_t)((val >> bits) & 0xFF);
      bits -= 8;
    }
  }
  return len;
}

void upscaleCoverBg(const uint16_t* src, int srcW, int srcH, uint16_t* dst, int dstW, int dstH) {
  if (!src || !dst) return;
  for (int dy = 0; dy < dstH; dy++) {
    int sy = (dy * srcH) / dstH;
    int dstRow = dy * dstW;
    int srcRow = sy * srcW;
    for (int dx = 0; dx < dstW; dx++) {
      int sx = (dx * srcW) / dstW;
      dst[dstRow + dx] = src[srcRow + sx];
    }
  }
}

// ----------------------------------------------------------------------------
// Forward declarations
// ----------------------------------------------------------------------------
void copyText(char* dst, size_t size, const char* src);
const char* pageName(ScreenPage value);
const char* modeName();
const char* expressionName(EyeExpression value);
EyeExpression expressionFromString(const char* value);
bool wakeActive(unsigned long now);
void triggerWake(unsigned long durationMs);
void beep(int frequency, int durationMs);
void doubleBeep();

void initButtons();
void initOled();
void initTft();
void initSensors();
void initMic();
void bootScreen();

void readEnvironment();
void readMotion();
void readMicrophone();
void computeFftFromMic();
void performGesture(int taps);
void updateBattery();
int  batteryPercent();
const char* batteryLabel();

void checkButtons();
void handleButton(int index);
void setPage(ScreenPage value);
void nextPage();
void previousPage();
void toggleMode();

void readSerial();
void handleBackendLine(const String& line);
void applyState(JsonObjectConst payload);
void applyNotification(JsonObjectConst payload);
void applyPomodoro(JsonObjectConst payload);
void applyMusic(JsonObjectConst payload);
uint8_t fontModeFromName(const char* face);
bool fontAAFromMode(uint8_t mode);
void applyCommand(JsonObjectConst payload);

void sendHeartbeat();
void sendSensorData();
void sendButton(const char* button);
void sendMusicAction(const char* action);
void sendPomodoroAction(const char* action);
void sendNotificationAck(const char* id);
void sendModeSwitched();
void sendGesture(const char* gesture);

void updateConnectivity(unsigned long now);
void updateExpression(unsigned long now);
void updatePomodoro();

void addNotification(const char* title, const char* message, int priority, const char* id);
void markFirstUnread();
int  unreadLocal();

void startPomodoro(int minutes);
void pausePomodoro();
void resetPomodoro();
void togglePomodoro();

void drawEyes(unsigned long now);
void drawEye(int cx, int cy, int w, int h, int r,
             int pupilDx, int pupilDy, int pupilR,
             int lidTopPercent, int lidBottomPercent);
void drawClosedEye(int cx, int cy, int w);
void drawBrows(int cx, int cy, bool angry, bool raised);
void drawNoteIcon(int x, int y);
void drawSparkle(int x, int y);
void drawStatusLabel();
void drawTft(unsigned long now);
void updateBacklight(unsigned long now);
const char* activityLabel();

// Voice assistant (Wi-Fi HTTP + MAX98357A I2S output)
void voiceInit();
void voiceTick(unsigned long now);
void voiceToggle();
void voiceCancel();
void voiceHandleCommand(JsonObjectConst payload);
void voiceSaveConfig(const char* ssid, const char* pass, const char* url);
void drawVoiceOverlay(unsigned long now);
bool voiceIsCapturing();

// ----------------------------------------------------------------------------
// Modern UI (sprite-based, anti-aliased)
// ----------------------------------------------------------------------------
// The framebuffer is touched per-pixel during software AA, so keep it in fast
// internal SRAM instead of letting malloc place the 40 KB canvas in PSRAM.
class InternalCanvas16 : public GFXcanvas16 {
 public:
  InternalCanvas16(uint16_t w, uint16_t h) : GFXcanvas16(w, h, false) {
    uint32_t bytes = (uint32_t)w * h * 2;
    buffer = (uint16_t*)heap_caps_malloc(bytes, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    if (!buffer) buffer = (uint16_t*)malloc(bytes);   // fall back if SRAM is tight
    if (buffer) { memset(buffer, 0, bytes); buffer_owned = false; }
  }
};
InternalCanvas16 sprite(128, 160);
#if defined(HAS_U8G2_GFX)
U8G2_FOR_ADAFRUIT_GFX u8g2gfx;
#endif
#define UI_FORCE_FULL_PUSH 1
#include "ui_modern.h"

// ----------------------------------------------------------------------------
// Small helpers
// ----------------------------------------------------------------------------
void copyText(char* dst, size_t size, const char* src) {
  if (dst == nullptr || size == 0) return;
  if (src == nullptr) {
    dst[0] = '\0';
    return;
  }
  strncpy(dst, src, size - 1);
  dst[size - 1] = '\0';
}

const char* pageName(ScreenPage value) {
  switch (value) {
    case PAGE_HOME: return "home";
    case PAGE_MUSIC: return "music";
    case PAGE_LYRICS: return "lyrics";
    case PAGE_PC: return "pc";
    case PAGE_ENV: return "environment";
    case PAGE_NOTIFICATIONS: return "notifications";
    case PAGE_POMODORO: return "pomodoro";
    case PAGE_FONT_TEST: return "font_test";
    default: return "home";
  }
}

const char* modeName() {
  return mode == MODE_INSPECTION ? "inspection" : "omnipect";
}

const char* expressionName(EyeExpression value) {
  switch (value) {
    case EXPR_RELAXED: return "relaxed";
    case EXPR_HAPPY: return "happy";
    case EXPR_SAD: return "sad";
    case EXPR_ANGRY: return "angry";
    case EXPR_SLEEPY: return "sleepy";
    case EXPR_THINKING: return "thinking";
    case EXPR_CURIOUS: return "curious";
    case EXPR_EXCITED: return "excited";
    case EXPR_SURPRISED: return "surprised";
    case EXPR_CONFUSED: return "confused";
    case EXPR_LAUGHING: return "laughing";
    case EXPR_MUSIC: return "music";
    case EXPR_TYPING: return "typing";
    case EXPR_CODING: return "coding";
    case EXPR_BROWSING: return "browsing";
    case EXPR_GAMING: return "gaming";
    case EXPR_WATCHING: return "watching";
    case EXPR_SLEEPING: return "sleeping";
    case EXPR_DEEP_SLEEP: return "deep_sleep";
    case EXPR_AUTONOMOUS: return "autonomous";
    case EXPR_TALKING:    return "talking";
    case EXPR_ALARMED:    return "alarmed";
    default: return "relaxed";
  }
}

EyeExpression expressionFromString(const char* value) {
  if (value == nullptr) return EXPR_RELAXED;
  if (strcmp(value, "happy") == 0) return EXPR_HAPPY;
  if (strcmp(value, "sad") == 0) return EXPR_SAD;
  if (strcmp(value, "angry") == 0) return EXPR_ANGRY;
  if (strcmp(value, "sleepy") == 0) return EXPR_SLEEPY;
  if (strcmp(value, "thinking") == 0) return EXPR_THINKING;
  if (strcmp(value, "curious") == 0) return EXPR_CURIOUS;
  if (strcmp(value, "excited") == 0) return EXPR_EXCITED;
  if (strcmp(value, "surprised") == 0) return EXPR_SURPRISED;
  if (strcmp(value, "confused") == 0) return EXPR_CONFUSED;
  if (strcmp(value, "laughing") == 0) return EXPR_LAUGHING;
  if (strcmp(value, "music") == 0) return EXPR_MUSIC;
  if (strcmp(value, "typing") == 0) return EXPR_TYPING;
  if (strcmp(value, "coding") == 0) return EXPR_CODING;
  if (strcmp(value, "browsing") == 0) return EXPR_BROWSING;
  if (strcmp(value, "gaming") == 0) return EXPR_GAMING;
  if (strcmp(value, "watching") == 0) return EXPR_WATCHING;
  if (strcmp(value, "sleeping") == 0) return EXPR_SLEEPING;
  if (strcmp(value, "deep_sleep") == 0) return EXPR_DEEP_SLEEP;
  if (strcmp(value, "autonomous") == 0) return EXPR_AUTONOMOUS;
  if (strcmp(value, "talking") == 0) return EXPR_TALKING;
  if (strcmp(value, "alarmed") == 0) return EXPR_ALARMED;
  return EXPR_RELAXED;
}

bool wakeActive(unsigned long now) {
  return wakeUntil != 0 && now < wakeUntil;
}

void triggerWake(unsigned long durationMs) {
  wakeUntil = millis() + durationMs;
  targetExpr = EXPR_HAPPY;
  currentExpr = EXPR_HAPPY;
  tftDirty = true;
}

void beep(int frequency, int durationMs) {
  if (PIN_SPEAKER >= 0) tone(PIN_SPEAKER, frequency, durationMs);
  playI2STone(frequency, durationMs);
}

void doubleBeep() {
  beep(1500, 70);
  delay(90);
  beep(1900, 90);
}

// ----------------------------------------------------------------------------
// Hardware setup
// ----------------------------------------------------------------------------
static unsigned long buttonPressStartMs[5] = {0, 0, 0, 0, 0};

void initButtons() {
  for (int i = 0; i < 5; i++) {
    gpio_num_t pin = (gpio_num_t)BUTTON_PINS[i];
    gpio_reset_pin(pin);
    pinMode(BUTTON_PINS[i], INPUT_PULLUP);
    gpio_pullup_en(pin);
    gpio_pulldown_dis(pin);
  }
  delay(10);
  for (int i = 0; i < 5; i++) {
    bool raw = (digitalRead(BUTTON_PINS[i]) == LOW);
    buttonLastRead[i] = raw;
    buttonStable[i] = raw;
    buttonPressed[i] = false;
    buttonDebounceMs[i] = millis();
    buttonPressStartMs[i] = 0;
  }
}

void initOled() {
  uint8_t detectedAddr = 0x3C;
  Wire.beginTransmission(0x3C);
  if (Wire.endTransmission() != 0) {
    Wire.beginTransmission(0x3D);
    if (Wire.endTransmission() == 0) {
      detectedAddr = 0x3D;
      Serial.println("[boot] OLED detected at 0x3D");
    } else {
      Serial.println("[boot] OLED not responding at 0x3C or 0x3D! Retrying 0x3C...");
    }
  } else {
    Serial.println("[boot] OLED detected at 0x3C");
  }

  oled.setI2CAddress(detectedAddr << 1);
  oled.begin();

  // Send hardware charge-pump & display-on commands for BOTH SSD1306 and SH1106
  Wire.beginTransmission(detectedAddr);
  Wire.write(0x00); // Command stream
  Wire.write(0x8D); // SSD1306 Charge pump command
  Wire.write(0x14); // SSD1306 Enable charge pump (7.5V)
  Wire.write(0xAD); // SH1106 DC-DC command
  Wire.write(0x8B); // SH1106 Enable DC-DC
  Wire.write(0xAF); // Display ON
  Wire.endTransmission();

  oled.setFont(u8g2_font_5x7_tf);
  oled.setContrast(255);
}

void initTft() {
  pinMode(PIN_TFT_BL, OUTPUT);
  analogWrite(PIN_TFT_BL, 220);
  lastBacklight = 220;

  SPI.begin(PIN_TFT_SCLK, -1, PIN_TFT_MOSI, PIN_TFT_CS);
  // Try GREENTAB (BGR color order by default) - may match this panel better.
  tft.initR(INITR_GREENTAB);
  tft.setRotation(2);
  tft.fillScreen(theme.bg);
  tft.setTextWrap(false);
  tft.setTextSize(1);
  tft.setTextColor(theme.text, theme.bg);
}

void initSensors() {
  sensors.bmeOk = bme.begin(0x77, &Wire);
  if (!sensors.bmeOk) {
    sensors.bmeOk = bme.begin(0x76, &Wire);
  }
  if (sensors.bmeOk) {
    bme.setSampling(Adafruit_BME280::MODE_NORMAL,
                    Adafruit_BME280::SAMPLING_X2,
                    Adafruit_BME280::SAMPLING_X16,
                    Adafruit_BME280::SAMPLING_X1,
                    Adafruit_BME280::FILTER_X16,
                    Adafruit_BME280::STANDBY_MS_500);
  }

  sensors.adxlOk = adxl.begin(0x53);
  if (sensors.adxlOk) {
    adxl.setRange(ADXL345_RANGE_4_G);
    adxl.setDataRate(ADXL345_DATARATE_100_HZ);
  }

  analogSetPinAttenuation(PIN_BATTERY, ADC_11db);
  sensors.temperature = NAN;
  sensors.humidity = NAN;
  sensors.pressure = NAN;
  sensors.batteryVoltage = 0.0f;
  sensors.micLevel = -1;
  sensors.micOk = false;
}

void initMic() {
  sensors.micLevel = -1;
  sensors.micOk = false;
  i2s.setPins(PIN_MIC_SCK, PIN_MIC_WS, -1, PIN_MIC_SD);
  if (!i2s.begin(I2S_MODE_STD, 16000, I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO)) {
    return;
  }
  i2s.setTimeout(5);
  sensors.micOk = true;
  sensors.micLevel = 0;
}

void bootScreen() {
  oled.clearBuffer();
  drawEye(40, 32, 36, 28, 10, 0, 0, 7, 0, 0);
  drawEye(88, 32, 36, 28, 10, 0, 0, 7, 0, 0);
  oled.setFont(u8g2_font_6x10_tf);
  oled.drawStr(40, 61, "Omnipect");
  oled.sendBuffer();

  uiBoot();
}

// ----------------------------------------------------------------------------
// Sensors
// ----------------------------------------------------------------------------
void updateBattery() {
  float milliVolts = (float)analogReadMilliVolts(PIN_BATTERY);
  float raw = 0.0f;
  if (milliVolts > 1.0f) {
    raw = (milliVolts * BATTERY_DIVIDER) / 1000.0f;
  } else {
    raw = ((float)analogRead(PIN_BATTERY) / 4095.0f) * 3.3f * BATTERY_DIVIDER;
  }

  if (raw <= 0.5f) return;
  if (sensors.batteryVoltage <= 0.5f) {
    sensors.batteryVoltage = raw;
  } else {
    sensors.batteryVoltage = (sensors.batteryVoltage * 0.8f) + (raw * 0.2f);
  }
}

void readEnvironment() {
  if (!sensors.bmeOk) return;

  float t = bme.readTemperature();
  float h = bme.readHumidity();
  float p = bme.readPressure() / 100.0f;
  if (!isnan(t) && t > -40.0f && t < 85.0f) sensors.temperature = t;
  if (!isnan(h) && h >= 0.0f && h <= 100.0f) sensors.humidity = h;
  if (!isnan(p) && p > 300.0f && p < 1200.0f) sensors.pressure = p;
}

void readMicrophone() {
  if (!sensors.micOk) return;

  size_t bytes = i2s.readBytes((char*)micBuffer, sizeof(micBuffer));
  size_t samples = bytes / sizeof(int32_t);
  if (samples == 0) return;

  // Remove DC offset before RMS so INMP441 bias doesn't skew readings.
  int64_t dcSum = 0;
  for (size_t i = 0; i < samples; i++) {
    dcSum += (int64_t)micBuffer[i];
  }
  double mean = (double)dcSum / (double)samples;

  double sum = 0.0;
  for (size_t i = 0; i < samples; i++) {
    double sample = (double)micBuffer[i] - mean;
    sum += sample * sample;
  }

  float rms = sqrt((float)(sum / samples));
  if (rms < 1.0f) rms = 1.0f;

  // INMP441 data is a 24-bit sample left-justified in a 32-bit slot.
  // Map -82..-22 dBFS to 0..100 so room speech and desk speakers register cleanly.
  float dbfs = 20.0f * log10f(rms / 2147483648.0f);
  float level = (dbfs + 82.0f) * (100.0f / 60.0f);
  level = constrain(level, 0.0f, 100.0f);

  if (level > micLevelSmoothed) {
    micLevelSmoothed = (micLevelSmoothed * 0.5f) + (level * 0.5f);
  } else {
    micLevelSmoothed = (micLevelSmoothed * 0.85f) + (level * 0.15f);
  }
  sensors.micLevel = (int)(micLevelSmoothed + 0.5f);

  // Update FFT visualizer data (cheap enough at 20 ms cadence).
  if (samples >= FFT_N) {
    computeFftFromMic();
  }
}

void computeFftFromMic() {
  const int N = FFT_N;
  if (sensors.micOk == false) return;

  // Collect N samples from micBuffer (already filled by readMicrophone).
  int64_t sum = 0;
  for (int i = 0; i < N; i++) sum += (int64_t)micBuffer[i];
  float mean = (float)((double)sum / (double)N);

  // Hann window + real input
  for (int i = 0; i < N; i++) {
    float w = 0.5f * (1.0f - cosf(2.0f * 3.14159265f * (float)i / (float)(N - 1)));
    fftRe[i] = ((float)micBuffer[i] - mean) * w;
    fftIm[i] = 0.0f;
  }

  // Iterative Cooley-Tukey FFT
  // bit reversal
  int j = 0;
  for (int i = 1; i < N; i++) {
    int bit = N >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      float tr = fftRe[i]; fftRe[i] = fftRe[j]; fftRe[j] = tr;
      float ti = fftIm[i]; fftIm[i] = fftIm[j]; fftIm[j] = ti;
    }
  }
  for (int len = 2; len <= N; len <<= 1) {
    float ang = -2.0f * 3.14159265f / (float)len;
    float wlenR = cosf(ang), wlenI = sinf(ang);
    for (int i = 0; i < N; i += len) {
      float wR = 1.0f, wI = 0.0f;
      for (int k = 0; k < len / 2; k++) {
        float uR = fftRe[i + k];
        float uI = fftIm[i + k];
        float vR = fftRe[i + k + len / 2] * wR - fftIm[i + k + len / 2] * wI;
        float vI = fftRe[i + k + len / 2] * wI + fftIm[i + k + len / 2] * wR;
        fftRe[i + k] = uR + vR;
        fftIm[i + k] = uI + vI;
        fftRe[i + k + len / 2] = uR - vR;
        fftIm[i + k + len / 2] = uI - vI;
        float nR = wR * wlenR - wI * wlenI;
        float nI = wR * wlenI + wI * wlenR;
        wR = nR; wI = nI;
      }
    }
  }

  // Magnitudes into FFT_BARS (skip DC, group bins)
  int binsPerBar = (N / 2) / FFT_BARS;
  if (binsPerBar < 1) binsPerBar = 1;
  for (int b = 0; b < FFT_BARS; b++) {
    float mag = 0.0f;
    int start = 1 + b * binsPerBar;
    int end = start + binsPerBar;
    if (end > N / 2) end = N / 2;
    for (int k = start; k < end; k++) {
      float m = sqrtf(fftRe[k] * fftRe[k] + fftIm[k] * fftIm[k]);
      if (m > mag) mag = m;
    }
    // smooth
    fftBins[b] = fftBins[b] * 0.6f + (mag / 400000.0f) * 0.4f;
    if (fftBins[b] > 1.0f) fftBins[b] = 1.0f;
    if (fftBins[b] < 0.0f) fftBins[b] = 0.0f;
  }

  // Beat detection from bass energy (first 3 bars)
  float bass = (fftBins[0] + fftBins[1] + fftBins[2]) / 3.0f;
  if (fftBassAvg <= 0.0f) fftBassAvg = bass;
  if (bass > fftBassAvg * 1.6f && bass > 0.12f && millis() - fftBeatMs > 220) {
    fftBeat = true;
    fftBeatMs = millis();
  } else {
    if (millis() - fftBeatMs > 120) fftBeat = false;
  }
  fftBassAvg = fftBassAvg * 0.85f + bass * 0.15f;
}

// Gesture tuning. Taps are short spikes; a shake is sustained motion, so the
// shake counter needs several samples inside one window to avoid treating a
// triple tap (which also produces several spikes) as a shake.
const float IMPACT_DELTA      = 12.0f;  // m/s^2 deviation that counts as a tap
const float MOTION_DELTA      = 4.5f;   // deviation that counts as motion
const int   SHAKE_SAMPLE_HITS = 10;     // hits inside SHAKE_WINDOW_MS
const unsigned long SHAKE_WINDOW_MS  = 600;
const unsigned long TAP_WINDOW_MS    = 700;
const unsigned long IMPACT_DEBOUNCE  = 150;

void performGesture(int taps) {
  unsigned long now = millis();
  gestureLockUntil = now + 700;
  shakeHits = 0;

  if (taps == 1) {
    triggerWake(1500);
    sendGesture("single_tap");
  } else if (taps == 2) {
    triggerWake(1500);
    setPage(PAGE_MUSIC);
    beep(1600, 60);
    sendGesture("double_tap");
  } else if (taps >= 3) {
    triggerWake(2500);
    beep(1900, 80);
    sendButton("voice");
    sendGesture("triple_tap");
  }
}

void readMotion() {
  if (!sensors.adxlOk) return;

  sensors_event_t event;
  adxl.getEvent(&event);
  if (event.type != SENSOR_TYPE_ACCELEROMETER) return;

  sensors.accelX = event.acceleration.x;
  sensors.accelY = event.acceleration.y;
  sensors.accelZ = event.acceleration.z;

  targetPupilX = constrain(sensors.accelX / 4.0f, -1.0f, 1.0f);
  targetPupilY = constrain(sensors.accelY / 4.0f, -1.0f, 1.0f);

  float magnitude = sqrt(sensors.accelX * sensors.accelX +
                         sensors.accelY * sensors.accelY +
                         sensors.accelZ * sensors.accelZ);
  float delta = fabs(magnitude - 9.81f);
  unsigned long now = millis();

  if (delta > MOTION_DELTA) {
    lastMotionMs = now;
    if (now - shakeWindowMs > SHAKE_WINDOW_MS) {
      shakeWindowMs = now;
      shakeHits = 0;
    }
    shakeHits++;
  }

  // A shake is sustained motion, not a single impact: return home and wake up.
  if (shakeHits >= SHAKE_SAMPLE_HITS &&
      now - lastShakeMs > 2200 &&
      now >= gestureLockUntil) {
    shakeHits = 0;
    tapCount = 0;
    lastShakeMs = now;
    gestureLockUntil = now + 900;
    setPage(PAGE_HOME);
    triggerWake(2000);
    targetExpr = EXPR_SURPRISED;
    currentExpr = EXPR_SURPRISED;
    beep(900, 60);
    sendGesture("shake");
    return;
  }

  // Count impact spikes. Consecutive spikes within TAP_WINDOW_MS form a tap
  // sequence; the sequence is classified once it goes quiet.
  if (delta > IMPACT_DELTA &&
      now - lastImpactMs > IMPACT_DEBOUNCE &&
      now >= gestureLockUntil) {
    lastImpactMs = now;
    if (tapCount == 0) tapWindowMs = now;
    if (tapCount < 4) tapCount++;
  }

  if (tapCount > 0 && now - lastImpactMs > TAP_WINDOW_MS) {
    int taps = tapCount;
    tapCount = 0;
    performGesture(taps);
  }
}

struct BatteryPoint {
  float voltage;
  int percent;
};

// Approximate 3S Li-ion discharge curve. Linear 9.0-12.6 V mapping reads
// misleadingly high in the middle of the pack; this table follows the knee.
static const BatteryPoint BATTERY_CURVE[] = {
  {12.60f, 100}, {12.20f, 90}, {11.90f, 80}, {11.70f, 70},
  {11.50f, 60},  {11.30f, 50}, {11.10f, 40}, {10.90f, 30},
  {10.70f, 20},  {10.40f, 10}, {10.00f, 5},  {9.00f, 0},
};
const int BATTERY_CURVE_POINTS = sizeof(BATTERY_CURVE) / sizeof(BATTERY_CURVE[0]);

int batteryPercent() {
  float voltage = sensors.batteryVoltage;
  if (voltage <= 0.8f) return state.backendBatteryPct;
  if (voltage > 4.0f && voltage < 5.5f) return -2;
  if (voltage >= BATTERY_CURVE[0].voltage) return 100;
  if (voltage <= BATTERY_CURVE[BATTERY_CURVE_POINTS - 1].voltage) return 0;

  for (int i = 0; i < BATTERY_CURVE_POINTS - 1; i++) {
    float highVoltage = BATTERY_CURVE[i].voltage;
    float lowVoltage = BATTERY_CURVE[i + 1].voltage;
    if (voltage <= highVoltage && voltage >= lowVoltage) {
      int highPercent = BATTERY_CURVE[i].percent;
      int lowPercent = BATTERY_CURVE[i + 1].percent;
      float t = (voltage - lowVoltage) / (highVoltage - lowVoltage);
      return constrain((int)(lowPercent + t * (highPercent - lowPercent) + 0.5f), 0, 100);
    }
  }
  return 0;
}

const char* batteryLabel() {
  static char label[18];
  int pct = batteryPercent();
  if (pct == -1) {
    snprintf(label, sizeof(label), "NO BATTERY");
  } else if (pct == -2) {
    snprintf(label, sizeof(label), "USB POWER");
  } else {
    snprintf(label, sizeof(label), "BAT %d%%", pct);
  }
  return label;
}

// ----------------------------------------------------------------------------
// Buttons and page navigation
// ----------------------------------------------------------------------------
// Remappable buttons. Numeric values match BUTTON_ACTIONS in the backend
// (app/services/device_settings.py) - do not reorder without updating both.
enum : uint8_t {
  BA_NEXT_PAGE, BA_PREV_PAGE, BA_PLAY_PAUSE, BA_VOL_UP, BA_VOL_DOWN,
  BA_TOGGLE_MODE, BA_VOICE, BA_NONE, BA_DEFAULT, BA_COUNT
};
uint8_t buttonMap[5][PAGE_COUNT];

void resetButtonMap() {
  for (int b = 0; b < 5; b++)
    for (int p = 0; p < PAGE_COUNT; p++) buttonMap[b][p] = BA_DEFAULT;
  for (int p = 0; p < PAGE_COUNT; p++) {
    buttonMap[0][p] = BA_TOGGLE_MODE;   // MODE
    buttonMap[1][p] = BA_VOICE;         // VOICE
    buttonMap[2][p] = BA_PREV_PAGE;     // UP
    buttonMap[3][p] = BA_NEXT_PAGE;     // DOWN
    buttonMap[4][p] = BA_DEFAULT;       // SELECT - contextual
  }
}

void handleButtonDefault(int index);

void checkButtons() {
  unsigned long now = millis();
  for (int i = 0; i < 5; i++) {
    bool pressed = digitalRead(BUTTON_PINS[i]) == LOW;
    if (pressed != buttonLastRead[i]) {
      buttonDebounceMs[i] = now;
      buttonLastRead[i] = pressed;
    }

    if (now - buttonDebounceMs[i] > 30 && pressed != buttonStable[i]) {
      buttonStable[i] = pressed;
      Serial.printf("[btn] pin=%d (%s) changed to %s (page=%d)\n",
                    BUTTON_PINS[i], BUTTON_NAMES[i], pressed ? "PRESSED" : "RELEASED", (int)page);
      Serial.flush();
      if (pressed) {
        buttonPressed[i] = true;
        buttonPressStartMs[i] = now;
        lastMotionMs = now;
        if (i != 0) { // MODE button evaluates on release to support short-tap (next page) vs hold (toggle mode)
          handleButton(i);
        }
      } else {
        buttonPressed[i] = false;
        if (i == 0) { // MODE button
          unsigned long duration = now - buttonPressStartMs[0];
          if (duration >= 500) {
            // Long press: Toggle between Omnipect and Industrial Inspection
            toggleMode();
          } else {
            // Short tap: Cycle to Next Page!
            nextPage();
          }
        }
      }
    }
  }
}

void handleButton(int index) {
  switch (buttonMap[index][page]) {
    case BA_NEXT_PAGE: nextPage(); break;
    case BA_PREV_PAGE: previousPage(); break;

    case BA_PLAY_PAUSE:
      state.musicPlaying = !state.musicPlaying;
      sendMusicAction(state.musicPlaying ? "play" : "pause");
      beep(state.musicPlaying ? 1500 : 900, 55);
      tftDirty = true;
      break;

    case BA_VOL_UP:   sendMusicAction("volume_up");   beep(1700, 35); break;
    case BA_VOL_DOWN: sendMusicAction("volume_down"); beep(800, 35); break;

    case BA_TOGGLE_MODE: toggleMode(); break;

    case BA_VOICE:
      triggerWake(2200);
      targetExpr = EXPR_CURIOUS;
      currentExpr = EXPR_CURIOUS;
      beep(1400, 55);
      sendButton("voice");
      voiceToggle();
      break;

    case BA_NONE:
      break;

    default:
      handleButtonDefault(index);
      break;
  }
}

void handleButtonDefault(int index) {
  switch (index) {
    case 0:  // MODE
      toggleMode();
      break;

    case 1:  // VOICE
      triggerWake(2200);
      targetExpr = EXPR_CURIOUS;
      currentExpr = EXPR_CURIOUS;
      beep(1400, 55);
      sendButton("voice");
      voiceToggle();
      break;

    case 2:  // UP
      previousPage();
      break;

    case 3:  // DOWN
      nextPage();
      break;

    case 4:  // SELECT
      if (mode == MODE_INSPECTION) {
        if (inspectResultReady) {
          // Reset for new capture
          inspectResultReady = false;
          inspectCount = 0;
          tftDirty = true;
          tftFullRedraw = true;
        } else if (!inspectCapturing) {
          // Start capture
          inspectCapturing = true;
          inspectCount = 0;
          inspectStartMs = millis();
          inspectResultReady = false;
          tftDirty = true;
          tftFullRedraw = true;
          beep(1200, 60);
        }
      } else if (page == PAGE_POMODORO) {
        togglePomodoro();
      } else if (page == PAGE_MUSIC || page == PAGE_LYRICS) {
        state.musicPlaying = !state.musicPlaying;
        sendMusicAction(state.musicPlaying ? "play" : "pause");
        beep(state.musicPlaying ? 1500 : 900, 55);
        tftDirty = true;
      } else if (page == PAGE_NOTIFICATIONS) {
        markFirstUnread();
      } else {
        nextPage();
      }
      break;
  }
}

void setPage(ScreenPage value) {
  if (value < 0 || value >= PAGE_COUNT) return;
  page = value;
  noticeOverride = false;
  noticeUntil = 0;
  tftDirty = true;
  tftFullRedraw = true;
  sendHeartbeat();
}

void nextPage() {
  setPage((ScreenPage)((page + 1) % PAGE_COUNT));
}

void previousPage() {
  setPage((ScreenPage)((page + PAGE_COUNT - 1) % PAGE_COUNT));
}

void toggleMode() {
  mode = (mode == MODE_OMNIPECT) ? MODE_INSPECTION : MODE_OMNIPECT;
  page = PAGE_HOME;
  tftDirty = true;
  tftFullRedraw = true;
  triggerWake(1500);
  beep(1200, 70);
  sendModeSwitched();
}

// ----------------------------------------------------------------------------
// Serial protocol
// ----------------------------------------------------------------------------
void readSerial() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      if (serialBufferOverflow) {
        serialBufferOverflow = false;
        serialBuffer = "";
      } else if (serialBuffer.length() > 0) {
        handleBackendLine(serialBuffer);
        serialBuffer = "";
      }
    } else if (c != '\r' && !serialBufferOverflow) {
      // The state packet grew with lyrics and telemetry. Allow room for
      // JSON-escaped non-ASCII text (Python escapes each character as \uXXXX)
      // and base64 cover art payloads.
      if (serialBuffer.length() < 8192) {
        serialBuffer += c;
      } else {
        serialBuffer = "";
        serialBufferOverflow = true;
      }
    }
  }
}

void handleBackendLine(const String& line) {
  rxDoc.clear();
  DeserializationError error = deserializeJson(rxDoc, line);
  if (error) {
    return;
  }

  const char* cmd = rxDoc["cmd"] | "";
  if (cmd[0] == '\0') {
    cmd = rxDoc["type"] | "";
  }

  JsonObjectConst payload = rxDoc["payload"].as<JsonObjectConst>();
  if (payload.isNull()) {
    payload = rxDoc.as<JsonObjectConst>();
  }

  if (strcmp(cmd, "omnipect_state") == 0 || strcmp(cmd, "deskbuddy_state") == 0) {
    applyState(payload);
  } else if (strcmp(cmd, "notification") == 0) {
    applyNotification(payload);
  } else if (strcmp(cmd, "pomodoro") == 0) {
    applyPomodoro(payload);
  } else if (strcmp(cmd, "music") == 0) {
    applyMusic(payload);
  } else if (strcmp(cmd, "cover_thumb") == 0) {
    const char* b64 = payload["data"] | "";
    const char* trk = payload["track"] | "";
    if (coverThumb != nullptr && b64[0] != '\0') {
      decodeBase64(b64, (uint8_t*)coverThumb, COVER_THUMB_W * COVER_THUMB_H * sizeof(uint16_t));
      hasCoverThumb = true;
      strncpy(coverTrack, trk, sizeof(coverTrack) - 1);
      coverTrack[sizeof(coverTrack) - 1] = '\0';
      uiOnCoverThumb();
      if (page == PAGE_MUSIC) {
        tftDirty = true;
        tftFullRedraw = true;
      }
    }
  } else if (strcmp(cmd, "cover_bg") == 0) {
    const char* b64 = payload["data"] | "";
    if (lyricsBg != nullptr && b64[0] != '\0') {
      static uint16_t tempSrc[COVER_BG_SRC_W * COVER_BG_SRC_H];
      decodeBase64(b64, (uint8_t*)tempSrc, sizeof(tempSrc));
      upscaleCoverBg(tempSrc, COVER_BG_SRC_W, COVER_BG_SRC_H, lyricsBg, TFT_W, TFT_H);
      hasLyricsBg = true;
      uiOnCoverBg();
      if (page == PAGE_LYRICS) {
        tftDirty = true;
        tftFullRedraw = true;
      }
    }
  } else if (strcmp(cmd, "inspection_result") == 0) {
    const char* cls = payload["predicted_class"] | "Unknown";
    float conf = payload["confidence"] | 0.0f;
    const char* axis = payload["worst_axis"] | "?";
    copyText(inspectResultClass, sizeof(inspectResultClass), cls);
    inspectResultConf = conf;
    copyText(inspectResultAxis, sizeof(inspectResultAxis), axis);
    inspectResultReady = true;
    inspectCapturing = false;
    tftDirty = true;
    tftFullRedraw = true;
    beep(1500, 100);
  } else if (strcmp(cmd, "set_theme") == 0) {
    const char* bg = payload["bg_color"] | "#000000";
    const char* text = payload["text_color"] | "#FFFFFF";
    const char* accent = payload["accent_color"] | "#07FF";
    const char* secondary = payload["secondary_color"] | "#8410";
    const char* warning = payload["warning_color"] | "#FD20";
    const char* success = payload["success_color"] | "#07E0";
    const char* danger = payload["danger_color"] | "#F800";
    const char* headerBg = payload["header_bg"] | "#0010";
    const char* headerText = payload["header_text"] | "#FFFFFF";
    theme.bg = hexToRgb565(bg);
    theme.text = hexToRgb565(text);
    theme.accent = hexToRgb565(accent);
    theme.secondary = hexToRgb565(secondary);
    theme.warning = hexToRgb565(warning);
    theme.success = hexToRgb565(success);
    theme.danger = hexToRgb565(danger);
    theme.headerBg = hexToRgb565(headerBg);
    theme.headerText = hexToRgb565(headerText);
    theme.titleSize = payload["title_size"] | 2;
    theme.bodySize = payload["body_size"] | 1;
    theme.bigSize = payload["big_size"] | 3;
    theme.timerSize = payload["timer_size"] | 4;
    // Apply immediately so the change is visible even if the main loop is
    // currently skipping redraws (e.g. deep-sleep / idle state).
    tft.fillScreen(theme.bg);
    tftDirty = true;
    tftFullRedraw = true;
    beep(1200, 60);
  } else if (strcmp(cmd, "set_buttons") == 0) {
    JsonArrayConst arr = payload["map"].as<JsonArrayConst>();
    int idx = 0;
    for (JsonVariantConst v : arr) {
      if (idx >= 5 * PAGE_COUNT) break;
      int a = v.as<int>();
      buttonMap[idx / PAGE_COUNT][idx % PAGE_COUNT] =
          (uint8_t)constrain(a, 0, (int)BA_COUNT - 1);
      idx++;
    }
    if (idx > 0) beep(1300, 40);
  } else if (strcmp(cmd, "set_font") == 0) {
    const char* face = payload["face"] | "pixel";
    uint8_t m = 0; bool aa = false;
    if (strcmp(face, "compact") == 0) { m = 1; aa = false; }
    else if (strcmp(face, "picopixel") == 0) { m = 2; aa = false; }
    else if (strcmp(face, "tiny3x3") == 0) { m = 3; aa = false; }
    else if (strcmp(face, "roboto") == 0) { m = 4; aa = true; }
    else if (strcmp(face, "inter") == 0) { m = 5; aa = true; }
    else if (strcmp(face, "montserrat") == 0) { m = 6; aa = true; }
    else if (strcmp(face, "jetbrainsmono") == 0) { m = 7; aa = true; }
    else { m = 0; aa = false; }
    uiFontFaceMode = m; uiFontAA = aa;
    // Propagate to per-element music fonts so the dashboard font menu
    // changes the music page too.
    uiMusicTitleFont = m;      uiMusicTitleAA = aa;
    uiMusicArtistFont = m;     uiMusicArtistAA = aa;
    uiMusicActiveLyricFont = m; uiMusicActiveLyricAA = aa;
    uiMusicUpcomingLyricFont = m; uiMusicUpcomingLyricAA = aa;
    uiMusicTimerFont = m;      uiMusicTimerAA = aa;
    uiMusicStatusFont = m;     uiMusicStatusAA = aa;
    int op = payload["opacity"] | -1;
    if (op >= 0) {
      wallpaperOpacity = (uint8_t)constrain(op, 0, 255);
      wallpaperVersion++;
    }
    tftDirty = true;
    tftFullRedraw = true;
  } else if (strcmp(cmd, "wallpaper_begin") == 0) {
    if (!wallpaperBuf) {
      wallpaperBuf = psramFound()
          ? (uint16_t*)ps_malloc(TFT_W * TFT_H * sizeof(uint16_t))
          : (uint16_t*)malloc(TFT_W * TFT_H * sizeof(uint16_t));
    }
    wallpaperTotal = (uint32_t)(payload["total"] | 0);
    wallpaperRecv = 0;
    hasWallpaper = false;
  } else if (strcmp(cmd, "wallpaper_chunk") == 0) {
    if (wallpaperBuf) {
      int seq = payload["seq"] | 0;
      const char* b64 = payload["data"] | "";
      if (seq >= 0 && seq <= (TFT_W * TFT_H * 2) / WALLPAPER_CHUNK && b64[0] != '\0') {
        long off = (long)seq * WALLPAPER_CHUNK;
        long room = (long)(TFT_W * TFT_H * 2) - off;
        int maxOut = (int)(room > WALLPAPER_CHUNK ? WALLPAPER_CHUNK : room);
        if (maxOut > 0) {
          int n = decodeBase64(b64, ((uint8_t*)wallpaperBuf) + off, maxOut);
          if (n > 0) wallpaperRecv = (uint32_t)off + (uint32_t)n;
        }
      }
    }
  } else if (strcmp(cmd, "wallpaper_end") == 0) {
    int op = payload["opacity"] | wallpaperOpacity;
    wallpaperOpacity = (uint8_t)constrain(op, 0, 255);
    hasWallpaper = (wallpaperBuf != nullptr) &&
                   (wallpaperRecv >= (uint32_t)(TFT_W * TFT_H * 2));
    wallpaperVersion++;
    tftDirty = true;
    tftFullRedraw = true;
    Serial.printf("[wallpaper] %s recv=%lu\n", hasWallpaper ? "ready" : "incomplete",
                  (unsigned long)wallpaperRecv);
  } else if (strcmp(cmd, "wallpaper_clear") == 0) {
    hasWallpaper = false;
    wallpaperVersion++;
    tftDirty = true;
    tftFullRedraw = true;
  } else if (strcmp(cmd, "mode_switch") == 0) {
    const char* requested = payload["mode"] | "omnipect";
    mode = (strcmp(requested, "inspection") == 0) ? MODE_INSPECTION : MODE_OMNIPECT;
    page = PAGE_HOME;
    tftDirty = true;
    tftFullRedraw = true;
    triggerWake(1200);
  } else if (strcmp(cmd, "page") == 0) {
    int index = payload["page"] | 0;
    setPage((ScreenPage)constrain(index, 0, (int)PAGE_COUNT - 1));
  } else if (strcmp(cmd, "brightness") == 0) {
    int level = payload["level"] | 220;
    level = constrain(level, 0, 255);
    analogWrite(PIN_TFT_BL, level);
    lastBacklight = level;
  } else if (strcmp(cmd, "play_tone") == 0) {
    int frequency = payload["frequency"] | 1200;
    int duration = payload["duration"] | 100;
    beep(frequency, duration);
  } else if (strcmp(cmd, "test_speaker") == 0) {
    playStartupMelody();
  } else if (strcmp(cmd, "led") == 0) {
    ledApplyCommand(payload);
    tftDirty = true;
  } else if (strcmp(cmd, "led_audio") == 0) {
    ledApplyAudio(payload);
  } else if (strcmp(cmd, "set_fonts") == 0) {
    const char* v;
    v = payload["title"] | ""; if (v[0]) { uiMusicTitleFont = fontModeFromName(v); uiMusicTitleAA = fontAAFromMode(uiMusicTitleFont); }
    v = payload["artist"] | ""; if (v[0]) { uiMusicArtistFont = fontModeFromName(v); uiMusicArtistAA = fontAAFromMode(uiMusicArtistFont); }
    v = payload["active_lyric"] | ""; if (v[0]) { uiMusicActiveLyricFont = fontModeFromName(v); uiMusicActiveLyricAA = fontAAFromMode(uiMusicActiveLyricFont); }
    v = payload["upcoming_lyric"] | ""; if (v[0]) { uiMusicUpcomingLyricFont = fontModeFromName(v); uiMusicUpcomingLyricAA = fontAAFromMode(uiMusicUpcomingLyricFont); }
    v = payload["timer"] | ""; if (v[0]) { uiMusicTimerFont = fontModeFromName(v); uiMusicTimerAA = fontAAFromMode(uiMusicTimerFont); }
    v = payload["status"] | ""; if (v[0]) { uiMusicStatusFont = fontModeFromName(v); uiMusicStatusAA = fontAAFromMode(uiMusicStatusFont); }
    tftDirty = true;
    tftFullRedraw = true;
  } else if (strcmp(cmd, "voice") == 0) {
    voiceHandleCommand(payload);
  } else if (strcmp(cmd, "wifi") == 0) {
    const char* ssid = payload["ssid"] | "";
    const char* pass = payload["pass"] | "";
    voiceSaveConfig(ssid[0] ? ssid : nullptr, pass[0] ? pass : nullptr, nullptr);
    WiFi.disconnect(true);
  } else if (strcmp(cmd, "voice_server") == 0) {
    const char* url = payload["url"] | "";
    if (url[0]) voiceSaveConfig(nullptr, nullptr, url);
  } else if (strcmp(cmd, "voice_config") == 0) {
    const char* ssid = payload["ssid"] | "";
    const char* pass = payload["pass"] | "";
    const char* url = payload["url"] | "";
    voiceSaveConfig(ssid[0] ? ssid : nullptr, pass[0] ? pass : nullptr, url[0] ? url : nullptr);
    WiFi.disconnect(true);
  } else if (strcmp(cmd, "get_status") == 0) {
    sendHeartbeat();
  } else if (strcmp(cmd, "get_sensors") == 0) {
    sendSensorData();
  } else if (strcmp(cmd, "read_buttons") == 0) {
    Serial.printf("[btns] mode(16)=%d, voice(17)=%d, up(19)=%d, down(18)=%d, sel(4)=%d\n",
                  digitalRead(16), digitalRead(17), digitalRead(19), digitalRead(18), digitalRead(4));
    Serial.flush();
  } else if (strcmp(cmd, "scan_i2c") == 0) {
    Serial.println("[cmd] scanning I2C bus...");
    for (uint8_t a = 1; a < 127; a++) {
      Wire.beginTransmission(a);
      if (Wire.endTransmission() == 0) {
        Serial.printf("[i2c] Found device at 0x%02X\n", a);
      }
    }
    Serial.println("[cmd] I2C scan complete.");
    Serial.flush();
  } else if (strcmp(cmd, "oled_test") == 0) {
    const char* chip = payload["chip"] | "sh1106";
    int addr = payload["addr"] | 0x3C;
    Serial.printf("[cmd] testing oled chip=%s addr=0x%02X\n", chip, addr);
    if (strcmp(chip, "ssd1306") == 0) {
      u8g2_Setup_ssd1306_i2c_128x64_noname_f(oled.getU8g2(), U8G2_R2, u8x8_byte_arduino_hw_i2c, u8x8_gpio_and_delay_arduino);
    } else {
      u8g2_Setup_sh1106_i2c_128x64_noname_f(oled.getU8g2(), U8G2_R2, u8x8_byte_arduino_hw_i2c, u8x8_gpio_and_delay_arduino);
    }
    oled.setI2CAddress(addr << 1);
    oled.begin();

    Wire.beginTransmission(addr);
    Wire.write(0x00);
    Wire.write(0x8D); Wire.write(0x14); // SSD1306 charge pump
    Wire.write(0xAD); Wire.write(0x8B); // SH1106 DC-DC
    Wire.write(0xAF);                   // Display ON
    Wire.endTransmission();

    oled.setContrast(255);
    oled.clearBuffer();
    oled.setFont(u8g2_font_10x20_tf);
    oled.drawStr(10, 36, "OLED OK!");
    oled.sendBuffer();
    Serial.println("[cmd] oled_test complete.");
    Serial.flush();
  }
}

void sendHeartbeat() {
  txDoc.clear();
  txDoc["type"] = "heartbeat";
  txDoc["firmware"] = FW_VERSION;
  txDoc["page"] = pageName(page);
  txDoc["mode"] = modeName();
  txDoc["expression"] = state.expression[0] ? state.expression : expressionName(currentExpr);
  txDoc["uptime"] = millis() / 1000UL;
  txDoc["heap"] = ESP.getFreeHeap();
  txDoc["battery"] = sensors.batteryVoltage;
  txDoc["bme"] = sensors.bmeOk;
  txDoc["adxl"] = sensors.adxlOk;
  txDoc["mic"] = sensors.micOk;
  sendTx(txDoc);
}

void sendSensorData() {
  txDoc.clear();
  txDoc["type"] = "sensor_data";
  JsonObject data = txDoc["data"].to<JsonObject>();
  data["battery"] = sensors.batteryVoltage;
  data["battery_pct"] = batteryPercent();
  data["mic_level"] = sensors.micLevel;

  if (sensors.bmeOk) {
    data["temp"] = sensors.temperature;
    data["humidity"] = sensors.humidity;
    data["pressure"] = sensors.pressure;
  }
  if (sensors.adxlOk) {
    JsonObject accel = data["accel"].to<JsonObject>();
    accel["x"] = sensors.accelX;
    accel["y"] = sensors.accelY;
    accel["z"] = sensors.accelZ;
  }
  char pinBuf[48];
  snprintf(pinBuf, sizeof(pinBuf), "M16:%d V17:%d U19:%d D18:%d S4:%d",
           digitalRead(16), digitalRead(17), digitalRead(19), digitalRead(18), digitalRead(4));
  data["pins"] = pinBuf;

  sendTx(txDoc);
}

void sendInspectionData() {
  txDoc.clear();
  txDoc["type"] = "inspection_data";
  JsonObject data = txDoc["data"].to<JsonObject>();
  JsonArray xArr = data["x"].to<JsonArray>();
  JsonArray yArr = data["y"].to<JsonArray>();
  JsonArray zArr = data["z"].to<JsonArray>();
  for (int i = 0; i < inspectCount; i++) {
    xArr.add(inspectX[i]);
    yArr.add(inspectY[i]);
    zArr.add(inspectZ[i]);
  }
  data["sample_rate_hz"] = 40;  // ~40 Hz sampling
  data["method"] = "cnn";

  sendTx(txDoc);
}

void sendButton(const char* button) {
  txDoc.clear();
  txDoc["type"] = "button";
  txDoc["button"] = button;
  txDoc["page"] = pageName(page);
  txDoc["mode"] = modeName();
  sendTx(txDoc);
}

void sendMusicAction(const char* action) {
  txDoc.clear();
  txDoc["type"] = "music";
  txDoc["action"] = action;
  sendTx(txDoc);
}

void sendPomodoroAction(const char* action) {
  txDoc.clear();
  txDoc["type"] = "pomodoro";
  txDoc["action"] = action;
  txDoc["minutes"] = POMODORO_WORK_SECONDS / 60;
  sendTx(txDoc);
}

void sendNotificationAck(const char* id) {
  txDoc.clear();
  txDoc["type"] = "notification_ack";
  txDoc["id"] = id;
  sendTx(txDoc);
}

void sendModeSwitched() {
  txDoc.clear();
  txDoc["type"] = "mode_switched";
  txDoc["mode"] = modeName();
  sendTx(txDoc);
}

void sendGesture(const char* gesture) {
  txDoc.clear();
  txDoc["type"] = "gesture";
  txDoc["gesture"] = gesture;
  txDoc["page"] = pageName(page);
  txDoc["mode"] = modeName();
  sendTx(txDoc);
}

// ----------------------------------------------------------------------------
// Backend state and commands
// ----------------------------------------------------------------------------
void applyState(JsonObjectConst p) {
  bool wasOnline = state.backendOnline;

  copyText(state.activity, sizeof(state.activity), p["act"] | "idle");
  copyText(state.expression, sizeof(state.expression), p["expr"] | "relaxed");
  copyText(state.sleepStage, sizeof(state.sleepStage), p["sleep"] | "active");
  copyText(state.appName, sizeof(state.appName), p["app"] | "");
  copyText(state.windowTitle, sizeof(state.windowTitle), p["win"] | "");

  state.idleSeconds = p["idle"] | 0;
  state.audioActive = ((p["audio"] | 0) != 0);
  state.cpu = p["cpu"] | -1.0f;
  state.mem = p["mem"] | -1.0f;
  state.gpu = p["gpu"] | -1.0f;
  state.cpuTemp = p["ctemp"] | -1.0f;
  state.thermalZone = p["tz"] | -1.0f;
  state.gpuTemp = p["gtemp"] | -1.0f;
  state.gpuMem = p["gmem"] | -1.0f;
  state.gpuVramMb = p["gvram"] | 0;
  state.gpuFan = p["gfan"] | -1.0f;

  copyText(state.musicTitle, sizeof(state.musicTitle), p["m_title"] | "");
  copyText(state.musicArtist, sizeof(state.musicArtist), p["m_artist"] | "");
  state.musicPlaying = ((p["m_play"] | 0) != 0);
  state.musicProgress = p["m_prog"] | 0;
  state.musicDuration = p["m_dur"] | 0;

  copyText(state.lyricPrev, sizeof(state.lyricPrev), p["lyr_prev"] | "");
  copyText(state.lyricCur, sizeof(state.lyricCur), p["lyr_cur"] | "");
  copyText(state.lyricNext, sizeof(state.lyricNext), p["lyr_next"] | "");
  state.lyricsAvailable = ((p["lyr_ok"] | 0) != 0);
  state.lyricsSynced = ((p["lyr_sync"] | 0) != 0);
  state.lyricIndex = p["lyr_idx"] | -1;
  state.lyricTotal = p["lyr_tot"] | 0;

  state.backendBatteryPct = p["batt"] | -1;
  state.backendBatteryChg = p["batt_chg"] | -1;

  state.unread = p["unread"] | 0;
  copyText(state.clockText, sizeof(state.clockText), p["clock"] | "--:--");
  copyText(state.dateText, sizeof(state.dateText), p["date"] | "");
  copyText(state.dowText, sizeof(state.dowText), p["dow"] | "");
  state.epoch = (long)(p["epoch"] | 0);

  // If a local sensor is missing, fall back to the backend's copy of the last
  // telemetry. This keeps the dashboard useful while a sensor is unplugged.
  if (!sensors.bmeOk) {
    float t = p["env_t"] | -999.0f;
    float h = p["env_h"] | -999.0f;
    float pressure = p["env_p"] | -999.0f;
    if (t > -900.0f) sensors.temperature = t;
    if (h > -900.0f) sensors.humidity = h;
    if (pressure > -900.0f) sensors.pressure = pressure;
  }
  if (sensors.batteryVoltage <= 0.8f) {
    float bv = p["batt_v"] | 0.0f;
    if (bv > 0.8f) sensors.batteryVoltage = bv;
  }

  state.lastStateMs = millis();
  state.stateReceived = true;
  state.backendOnline = true;

  if (!wasOnline) {
    triggerWake(1800);
  }

  EyeExpression next = expressionFromString(state.expression);
  if (strcmp(state.sleepStage, "deep_sleep") == 0) {
    next = EXPR_DEEP_SLEEP;
  } else if (strcmp(state.sleepStage, "sleeping") == 0) {
    next = EXPR_SLEEPING;
  } else if (strcmp(state.sleepStage, "sleepy") == 0) {
    next = EXPR_SLEEPY;
  }

  if (!wakeActive(millis())) {
    targetExpr = next;
    currentExpr = next;
  }

  tftDirty = true;
}

void applyNotification(JsonObjectConst p) {
  const char* title = p["title"] | "Notification";
  const char* message = p["message"] | "";
  int priority = p["priority"] | 1;
  const char* id = p["id"] | "";
  addNotification(title, message, priority, id);
}

void applyPomodoro(JsonObjectConst p) {
  const char* action = p["action"] | "";
  int minutes = p["minutes"] | 25;

  if (strcmp(action, "start") == 0) {
    startPomodoro(minutes);
  } else if (strcmp(action, "pause") == 0) {
    pausePomodoro();
  } else if (strcmp(action, "reset") == 0) {
    resetPomodoro();
  }
  tftDirty = true;
}

uint8_t fontModeFromName(const char* face) {
  if (face == nullptr) return 0;
  if (strcmp(face, "compact") == 0) return 1;
  if (strcmp(face, "picopixel") == 0) return 2;
  if (strcmp(face, "tiny3x3") == 0) return 3;
  if (strcmp(face, "roboto") == 0) return 4;
  if (strcmp(face, "inter") == 0) return 5;
  if (strcmp(face, "montserrat") == 0) return 6;
  if (strcmp(face, "jetbrainsmono") == 0) return 7;
  return 0;
}

bool fontAAFromMode(uint8_t mode) {
  return mode >= 4;
}

void applyMusic(JsonObjectConst p) {
  const char* action = p["action"] | "";
  if (strcmp(action, "play") == 0) {
    state.musicPlaying = true;
  } else if (strcmp(action, "pause") == 0) {
    state.musicPlaying = false;
  }
  tftDirty = true;
}

// ----------------------------------------------------------------------------
// Notifications
// ----------------------------------------------------------------------------
void addNotification(const char* title, const char* message, int priority, const char* id) {
  if (id != nullptr && id[0] != '\0') {
    for (int i = 0; i < noteCount; i++) {
      if (strcmp(notes[i].id, id) == 0) {
        return;
      }
    }
  }

  if (noteCount >= 8) {
    for (int i = 7; i > 0; i--) {
      notes[i] = notes[i - 1];
    }
    noteCount = 7;
  } else {
    for (int i = noteCount; i > 0; i--) {
      notes[i] = notes[i - 1];
    }
  }

  copyText(notes[0].id, sizeof(notes[0].id), id);
  copyText(notes[0].title, sizeof(notes[0].title), title);
  copyText(notes[0].message, sizeof(notes[0].message), message);
  notes[0].priority = priority;
  notes[0].read = false;
  noteCount++;

  state.unread = unreadLocal();
  if (!noticeOverride) {
    pageBeforeNotice = page;
  }
  noticeOverride = true;
  noticeUntil = millis() + NOTICE_HOLD_MS;
  page = PAGE_NOTIFICATIONS;
  tftDirty = true;

  triggerWake(2500);
  doubleBeep();
}

void markFirstUnread() {
  for (int i = 0; i < noteCount; i++) {
    if (!notes[i].read) {
      notes[i].read = true;
      state.unread = unreadLocal();
      if (notes[i].id[0] != '\0') {
        sendNotificationAck(notes[i].id);
      }
      beep(1200, 50);
      tftDirty = true;
      return;
    }
  }
  beep(700, 40);
}

int unreadLocal() {
  int count = 0;
  for (int i = 0; i < noteCount; i++) {
    if (!notes[i].read) count++;
  }
  return count;
}

// ----------------------------------------------------------------------------
// Pomodoro
// ----------------------------------------------------------------------------
void startPomodoro(int minutes) {
  if (minutes <= 0) minutes = 25;
  minutes = constrain(minutes, 1, 180);
  pomodoro.running = true;
  pomodoro.isBreak = false;
  pomodoro.remaining = minutes * 60;
  pomodoro.session = 0;
  pomodoro.lastTick = millis();
  tftDirty = true;
  beep(1500, 70);
}

void pausePomodoro() {
  pomodoro.running = false;
  tftDirty = true;
  beep(900, 50);
}

void resetPomodoro() {
  pomodoro.running = false;
  pomodoro.isBreak = false;
  pomodoro.remaining = POMODORO_WORK_SECONDS;
  pomodoro.session = 0;
  pomodoro.lastTick = millis();
  tftDirty = true;
  beep(800, 60);
}

void togglePomodoro() {
  if (pomodoro.running) {
    pausePomodoro();
    sendPomodoroAction("pause");
  } else {
    if (pomodoro.remaining > 0 && (pomodoro.remaining < POMODORO_WORK_SECONDS || pomodoro.isBreak)) {
      pomodoro.running = true;
      pomodoro.lastTick = millis();
      tftDirty = true;
      beep(1500, 70);
    } else {
      startPomodoro(25);
    }
    sendPomodoroAction("start");
  }
}

void updatePomodoro() {
  if (!pomodoro.running) return;

  unsigned long now = millis();
  if (now - pomodoro.lastTick < 1000) return;
  pomodoro.lastTick += 1000;

  if (pomodoro.remaining > 0) {
    pomodoro.remaining--;
  }

  if (pomodoro.remaining <= 0) {
    if (pomodoro.isBreak) {
      pomodoro.isBreak = false;
      pomodoro.remaining = POMODORO_WORK_SECONDS;
      addNotification("Break over", "Back to focus", 2, "");
    } else {
      pomodoro.session++;
      if (pomodoro.session % 4 == 0) {
        pomodoro.isBreak = true;
        pomodoro.remaining = POMODORO_LONG_SECONDS;
        addNotification("Long break", "Take 15 minutes", 2, "");
      } else {
        pomodoro.isBreak = true;
        pomodoro.remaining = POMODORO_SHORT_SECONDS;
        addNotification("Break time", "Take 5 minutes", 2, "");
      }
    }
    doubleBeep();
  }

  tftDirty = true;
}

// ----------------------------------------------------------------------------
// Connectivity, autonomous mode and expression selection
// ----------------------------------------------------------------------------
void updateConnectivity(unsigned long now) {
  bool online = state.stateReceived && (now - state.lastStateMs <= STATE_TIMEOUT_MS);
  if (online != state.backendOnline) {
    state.backendOnline = online;
    tftDirty = true;
  }

  if (online) {
    return;
  }

  if (now >= nextAutonomousMs) {
    unsigned long quiet = now - max(lastMotionMs, lastButtonMs);
    if (!state.stateReceived) {
      targetExpr = EXPR_AUTONOMOUS;
    } else if (quiet > 300000UL) {
      targetExpr = EXPR_SLEEPING;
    } else if (quiet > 120000UL) {
      targetExpr = EXPR_SLEEPY;
    } else {
      int pick = random(0, 6);
      switch (pick) {
        case 0: targetExpr = EXPR_RELAXED; break;
        case 1: targetExpr = EXPR_HAPPY; break;
        case 2: targetExpr = EXPR_CURIOUS; break;
        case 3: targetExpr = EXPR_THINKING; break;
        case 4: targetExpr = EXPR_SURPRISED; break;
        default: targetExpr = EXPR_RELAXED; break;
      }
    }
    nextAutonomousMs = now + random(12000, 30000);
    tftDirty = true;
  }
}

void updateExpression(unsigned long now) {
  if (wakeActive(now)) {
    currentExpr = EXPR_HAPPY;
  } else {
    currentExpr = targetExpr;
  }

  if (currentExpr != EXPR_SLEEPING && currentExpr != EXPR_DEEP_SLEEP) {
    if (blinking && now >= blinkUntil) {
      blinking = false;
    }
    if (!blinking && now >= nextBlinkMs) {
      blinking = true;
      blinkUntil = now + 120;
      nextBlinkMs = now + random(2500, 5500);
    }
  } else {
    blinking = false;
  }

  pupilX += (targetPupilX - pupilX) * 0.25f;
  pupilY += (targetPupilY - pupilY) * 0.25f;
}

const char* activityLabel() {
  static char label[20];
  if (mode == MODE_INSPECTION) return "INSPECTION";
  if (wakeActive(millis())) return "HELLO";
  if (!state.backendOnline) return "AUTONOMOUS";
  if (strcmp(state.sleepStage, "deep_sleep") == 0) return "";
  if (strcmp(state.sleepStage, "sleeping") == 0) return "SLEEPING";
  if (strcmp(state.sleepStage, "sleepy") == 0) return "SLEEPY";

  copyText(label, sizeof(label), state.activity);
  for (char* c = label; *c != '\0'; c++) {
    if (*c >= 'a' && *c <= 'z') *c = (char)(*c - 32);
  }
  return label;
}

// ----------------------------------------------------------------------------
// OLED face
// ----------------------------------------------------------------------------
void drawEye(int cx, int cy, int w, int h, int r,
             int pupilDx, int pupilDy, int pupilR,
             int lidTopPercent, int lidBottomPercent) {
  oled.setDrawColor(1);
  oled.drawRBox(cx - w / 2, cy - h / 2, w, h, r);

  if (lidTopPercent > 0) {
    int lid = (h * lidTopPercent) / 100;
    oled.setDrawColor(0);
    oled.drawBox(cx - w / 2, cy - h / 2, w, lid);
    oled.setDrawColor(1);
    oled.drawHLine(cx - w / 2 + 3, cy - h / 2 + lid, w - 6);
  }

  if (lidBottomPercent > 0) {
    int lid = (h * lidBottomPercent) / 100;
    oled.setDrawColor(0);
    oled.drawBox(cx - w / 2, cy + h / 2 - lid, w, lid);
    oled.setDrawColor(1);
    oled.drawHLine(cx - w / 2 + 3, cy + h / 2 - lid, w - 6);
  }

  int minX = cx - w / 2 + pupilR + 3;
  int maxX = cx + w / 2 - pupilR - 3;
  int minY = cy - h / 2 + pupilR + 3;
  int maxY = cy + h / 2 - pupilR - 3;
  int px = constrain(cx + pupilDx, minX, maxX);
  int py = constrain(cy + pupilDy, minY, maxY);

  // Pupil base
  oled.setDrawColor(0);
  oled.drawDisc(px, py, pupilR);

  // Dual specular glints for 3D depth & life
  oled.setDrawColor(1);
  int glintR = pupilR / 3;
  if (glintR < 1) glintR = 1;
  oled.drawDisc(px - pupilR / 3, py - pupilR / 3, glintR);
  if (pupilR >= 5) {
    oled.drawPixel(px + pupilR / 3, py + pupilR / 3);
  }
}

void drawClosedEye(int cx, int cy, int w) {
  oled.setDrawColor(1);
  oled.drawRBox(cx - w / 2, cy - 2, w, 4, 2);
  oled.drawLine(cx - w / 2 + 4, cy + 2, cx + w / 2 - 4, cy + 2);
}

void drawBrows(int cx, int cy, bool angry, bool raised) {
  int y = cy - 21;
  oled.setDrawColor(1);

  if (angry) {
    if (cx < 64) {
      oled.drawLine(cx - 16, y - 2, cx + 10, y + 3);
      oled.drawLine(cx - 16, y - 1, cx + 10, y + 4);
    } else {
      oled.drawLine(cx - 10, y + 3, cx + 16, y - 2);
      oled.drawLine(cx - 10, y + 4, cx + 16, y - 1);
    }
  } else if (raised) {
    oled.drawLine(cx - 15, y, cx + 12, y - 2);
    oled.drawLine(cx - 15, y + 1, cx + 12, y - 1);
  } else {
    oled.drawLine(cx - 13, y, cx + 10, y);
  }
}

void drawNoteIcon(int x, int y) {
  oled.setDrawColor(1);
  oled.drawDisc(x, y, 3);
  oled.drawVLine(x + 3, y - 12, 12);
  oled.drawLine(x + 3, y - 12, x + 9, y - 10);
  oled.drawLine(x + 3, y - 9, x + 9, y - 7);
}

void drawSparkle(int x, int y) {
  oled.setDrawColor(1);
  oled.drawVLine(x, y - 3, 7);
  oled.drawHLine(x - 3, y, 7);
}

// Animated voice waveform bars at bottom-centre (TALKING expression)
void drawWaveformMouth(unsigned long now) {
  oled.setDrawColor(1);
  // 5 bars with sine-offset phases — heights 2..8
  int bars[5];
  for (int i = 0; i < 5; i++) {
    float phase = now / 180.0f + i * 0.9f;
    bars[i] = 2 + (int)(abs(sin(phase)) * 6.0f);
  }
  int startX = 42;
  for (int i = 0; i < 5; i++) {
    int bx = startX + i * 7;
    int bh = bars[i];
    oled.drawRBox(bx, 54 - bh, 5, bh, 1);
  }
}

// Pulsing dashed alert border frame (ALARMED expression)
void drawAlertFrame(unsigned long now) {
  oled.setDrawColor(1);
  bool pulse = ((now / 300) % 2) == 0;
  if (pulse) {
    // Corner brackets — 4 corners, 6px lines
    oled.drawHLine(0,  0,  12); oled.drawVLine(0,  0, 10);
    oled.drawHLine(116, 0, 12); oled.drawVLine(127, 0, 10);
    oled.drawHLine(0,  63, 12); oled.drawVLine(0, 54, 10);
    oled.drawHLine(116,63, 12); oled.drawVLine(127,54, 10);
    // Exclamation mark centred at bottom
    oled.drawVLine(63, 54, 5);
    oled.drawPixel(63, 61);
  }
}

void drawStatusLabel() {
  const char* label = activityLabel();
  if (label[0] == '\0') return;
  oled.setFont(u8g2_font_5x7_tf);
  int width = oled.getStrWidth(label);
  int x = (128 - width) / 2;
  if (x < 0) x = 0;
  oled.setDrawColor(1);
  oled.drawStr(x, 62, label);
}

void drawEyes(unsigned long now) {
  bool deep = (strcmp(state.sleepStage, "deep_sleep") == 0) ||
              (currentExpr == EXPR_DEEP_SLEEP);

  if (deep && !wakeActive(now)) {
    oled.setContrast(45);
    oled.clearBuffer();
    oled.setFont(u8g2_font_10x20_tf);
    oled.drawStr(38, 30, "Z");
    oled.setFont(u8g2_font_6x10_tf);
    oled.drawStr(58, 42, "z");
    oled.drawStr(72, 52, "z");
    oled.sendBuffer();
    return;
  }

  if (strcmp(state.sleepStage, "sleeping") == 0 && !wakeActive(now)) {
    oled.setContrast(90);
  } else {
    oled.setContrast(255);
  }

  oled.clearBuffer();

  // Natural biological saccades (micro-darts every 1.8 to 4.2 seconds)
  static unsigned long nextSaccadeMs = 0;
  static int saccadeX = 0;
  static int saccadeY = 0;
  if (now > nextSaccadeMs) {
    saccadeX = random(-2, 3);
    saccadeY = random(-1, 2);
    nextSaccadeMs = now + random(1800, 4200);
  }

  // Idle breathing oscillation (gentle sine wave)
  int breatheY = (int)(sin(now / 950.0f) * 1.5f);

  int px = (int)(pupilX * 7.0f) + saccadeX;
  int py = (int)(pupilY * 4.0f) + saccadeY;

  // Music beat vertical bounce
  int musicBounce = 0;
  if (state.musicPlaying) {
    musicBounce = (int)(abs(sin(now / 220.0f)) * 3.0f);
  }

  // Inspection mode tech HUD
  if (mode == MODE_INSPECTION) {
    oled.setDrawColor(1);
    oled.drawHLine(18, 16, 5); oled.drawVLine(18, 16, 5);
    oled.drawHLine(58, 16, 5); oled.drawVLine(62, 16, 5);
    oled.drawHLine(18, 48, 5); oled.drawVLine(18, 44, 5);
    oled.drawHLine(58, 48, 5); oled.drawVLine(62, 44, 5);

    oled.drawHLine(66, 16, 5); oled.drawVLine(66, 16, 5);
    oled.drawHLine(106, 16, 5); oled.drawVLine(110, 16, 5);
    oled.drawHLine(66, 48, 5); oled.drawVLine(66, 44, 5);
    oled.drawHLine(106, 48, 5); oled.drawVLine(110, 44, 5);

    if (inspectCapturing) {
      px += random(-2, 3);
      py += random(-2, 3);
    }
  }

  if (blinking && currentExpr != EXPR_SLEEPING && currentExpr != EXPR_DEEP_SLEEP) {
    drawClosedEye(40, 32 + breatheY + musicBounce, 34);
    drawClosedEye(88, 32 + breatheY + musicBounce, 34);
    drawStatusLabel();
    oled.sendBuffer();
    return;
  }

  switch (currentExpr) {

    // ── HAPPY: wide bright eyes, lifted lid, subtle bounce ──────────────────
    case EXPR_HAPPY: {
      int ey = 30 + breatheY + musicBounce;
      drawEye(40, ey, 36, 28, 10, px, py, 7, 0, 38);
      drawEye(88, ey, 36, 28, 10, px, py, 7, 0, 38);
      // Small upward-curved mouth arc
      oled.setDrawColor(1);
      for (int i = -8; i <= 8; i++) {
        int my = 55 - (int)(0.07f * i * i);
        oled.drawPixel(64 + i, my);
      }
      break;
    }

    // ── LAUGHING: squinted, big mouth, body shake ────────────────────────────
    case EXPR_LAUGHING: {
      int shake = (int)(sin(now / 80.0f) * 2.0f);
      int ey = 30 + breatheY + shake;
      drawEye(40 + shake, ey, 34, 24, 9, px, py, 6, 0, 56);
      drawEye(88 + shake, ey, 34, 24, 9, px, py, 6, 0, 56);
      // Open laugh mouth — ellipse outline
      oled.setDrawColor(1);
      oled.drawEllipse(64, 55, 9, 5, U8G2_DRAW_ALL);
      oled.setDrawColor(0);
      oled.drawDisc(64, 55, 5);   // hollow inside
      oled.setDrawColor(1);
      oled.drawStr(100, 48, "ha");
      break;
    }

    // ── EXCITED: huge eyes, triple sparkle, jumping bounce ─────────────────
    case EXPR_EXCITED: {
      int ey = 31 + breatheY + (int)(abs(sin(now / 150.0f)) * 4.0f);
      drawEye(40, ey, 38, 30, 11, px, py, 7, 0, 32);
      drawEye(88, ey, 38, 30, 11, px, py, 7, 0, 32);
      drawSparkle(16, 20);
      drawSparkle(112, 20);
      drawSparkle(64, 10);
      drawSparkle(16, 48);
      drawSparkle(112, 48);
      break;
    }

    // ── SURPRISED: dilated pupils, raised brows, mouth O ───────────────────
    case EXPR_SURPRISED: {
      int ey = 32 + breatheY;
      drawEye(40, ey, 44, 36, 14, px / 2, py / 2, 4, 0, 0);
      drawEye(88, ey, 44, 36, 14, px / 2, py / 2, 4, 0, 0);
      drawBrows(40, ey, false, true);
      drawBrows(88, ey, false, true);
      oled.setDrawColor(1);
      oled.drawEllipse(64, 56, 5, 4, U8G2_DRAW_ALL);
      break;
    }

    // ── ANGRY: lowered brows, narrowed eyes, inner glow ────────────────────
    case EXPR_ANGRY: {
      int ey = 33 + breatheY;
      drawEye(40, ey, 36, 24, 9, px, py, 5, 0, 0);
      drawEye(88, ey, 36, 24, 9, px, py, 5, 0, 0);
      drawBrows(40, ey, true, false);
      drawBrows(88, ey, true, false);
      // Frown
      oled.setDrawColor(1);
      for (int i = -7; i <= 7; i++) {
        int my = 53 + (int)(0.07f * i * i);
        oled.drawPixel(64 + i, my);
        oled.drawPixel(64 + i, my + 1);
      }
      break;
    }

    // ── SAD: drooping lids, downward brows, teardrop ────────────────────────
    case EXPR_SAD: {
      int ey = 34 + breatheY;
      drawEye(40, ey, 36, 26, 10, px, py + 2, 6, 20, 0);
      drawEye(88, ey, 36, 26, 10, px, py + 2, 6, 20, 0);
      drawBrows(40, ey, false, false);
      drawBrows(88, ey, false, false);
      // Animated teardrop under left eye
      int tdY = 44 + (int)((now / 500) % 10);
      oled.setDrawColor(1);
      oled.drawDisc(35, tdY, 2);
      oled.drawVLine(35, tdY + 2, 3);
      break;
    }

    // ── SLEEPY: heavy lid closure, slow pupil droop ─────────────────────────
    case EXPR_SLEEPY: {
      int ey = 34 + breatheY;
      int lidClose = 44 + (int)(sin(now / 1200.0f) * 10.0f);  // lid flutters
      drawEye(40, ey, 36, 26, 10, px, py + 3, 6, lidClose, 0);
      drawEye(88, ey, 36, 26, 10, px, py + 3, 6, lidClose, 0);
      oled.setFont(u8g2_font_6x10_tf);
      oled.setDrawColor(1);
      oled.drawStr(100, 32, "z");
      break;
    }

    // ── SLEEPING: flat eyes, drifting Zs ───────────────────────────────────
    case EXPR_SLEEPING: {
      drawClosedEye(40, 32, 34);
      drawClosedEye(88, 32, 34);
      // Cascading Z sizes, slow drift
      int zOff = (int)(now / 600) % 12;
      oled.setFont(u8g2_font_10x20_tf);
      oled.setDrawColor(1);
      oled.drawStr(100, 20 + zOff, "Z");
      oled.setFont(u8g2_font_6x10_tf);
      oled.drawStr(112, 32 + zOff, "z");
      oled.drawStr(118, 42 + zOff, "z");
      break;
    }

    // ── THINKING: eyes up-left, orbiting thought dot ────────────────────────
    case EXPR_THINKING: {
      int ey = 32 + breatheY;
      drawEye(40, ey, 36, 28, 10, -5, -4, 6, 0, 0);
      drawEye(88, ey + 1, 36, 28, 10, -3, -6, 6, 30, 0);
      // Orbiting dot around top-right of head
      float ang = now / 600.0f;
      int ox = 110 + (int)(cos(ang) * 7);
      int oy = 18 + (int)(sin(ang) * 7);
      oled.setDrawColor(1);
      oled.drawDisc(ox, oy, 2);
      oled.setFont(u8g2_font_6x10_tf);
      oled.drawStr(46, 58, ". . .");
      break;
    }

    // ── CURIOUS: asymmetric pupils, one raised brow ─────────────────────────
    case EXPR_CURIOUS: {
      int ey = 32 + breatheY;
      drawEye(40, ey, 36, 28, 10, px + 6, py - 2, 6, 0, 0);
      drawEye(88, ey, 36, 28, 10, px + 4, py + 1, 7, 0, 0);
      drawBrows(88, ey, false, true);
      // Tilted question mark
      oled.setFont(u8g2_font_6x10_tf);
      oled.setDrawColor(1);
      oled.drawStr(118, 36, "?");
      break;
    }

    // ── CONFUSED: mismatched eyes, spinning ? ───────────────────────────────
    case EXPR_CONFUSED: {
      int ey = 33 + breatheY;
      drawEye(40, ey, 36, 28, 10, -6, 2, 6, 32, 0);
      drawEye(88, ey - 1, 42, 30, 13, 6, -3, 5, 0, 0);
      // Rotating '?' orbiting centre top
      float angQ = now / 800.0f;
      int qx = 64 + (int)(cos(angQ) * 12);
      int qy = 12 + (int)(sin(angQ) * 5);
      oled.setFont(u8g2_font_5x7_tf);
      oled.setDrawColor(1);
      oled.drawStr(qx, qy, "?");
      break;
    }

    // ── MUSIC: beat-synced bounce, dancing notes ────────────────────────────
    case EXPR_MUSIC: {
      float beat = abs(sin(now / 240.0f));
      int ey = 30 + breatheY + (int)(beat * 4.0f);
      int eyeW = 34 + (int)(beat * 4.0f);
      drawEye(40, ey, eyeW, 28, 10, px, (int)(sin(now / 240.0f) * 3.0f), 7, 0, 0);
      drawEye(88, ey, eyeW, 28, 10, px, (int)(sin(now / 240.0f) * 3.0f), 7, 0, 0);
      drawNoteIcon(108, 48);
      // Second note offset
      oled.setDrawColor(1);
      oled.drawDisc(118, 54, 3);
      oled.drawVLine(121, 42, 12);
      // EQ-style bottom bars (3 bars, beat-driven)
      for (int b = 0; b < 3; b++) {
        float ph = now / 180.0f + b * 1.1f;
        int bh = 2 + (int)(abs(sin(ph)) * 5.0f);
        oled.drawRBox(14 + b * 5, 58 - bh, 4, bh, 1);
      }
      break;
    }

    // ── CODING: focused lean, blinking cursor ─────────────────────────────
    case EXPR_CODING: {
      int ey = 31 + breatheY;
      drawEye(40, ey, 36, 28, 10, px - 1, py + 2, 6, 0, 0);
      drawEye(88, ey, 36, 28, 10, px + 1, py + 2, 6, 0, 0);
      oled.setFont(u8g2_font_6x10_tf);
      oled.setDrawColor(1);
      oled.drawStr(94, 56, ">_");
      // Blinking block cursor
      if ((now / 500) % 2 == 0) {
        oled.drawBox(106, 48, 5, 7);
      }
      break;
    }

    // ── BROWSING: eyes scan left-right, loading dots ───────────────────────
    case EXPR_BROWSING: {
      int ey = 32 + breatheY;
      float scan = sin(now / 650.0f);
      int scanX = (int)(scan * 7.0f);
      drawEye(40, ey, 36, 28, 10, scanX, py, 6, 0, 0);
      drawEye(88, ey, 36, 28, 10, scanX, py, 6, 0, 0);
      // Spinning loader arc at bottom
      float ang = now / 300.0f;
      int lx = 64 + (int)(cos(ang) * 7);
      int ly = 57 + (int)(sin(ang) * 3);
      oled.setDrawColor(1);
      oled.drawDisc(lx, ly, 2);
      break;
    }

    // ── GAMING: dilated, tense, corner HUD sparks ────────────────────────
    case EXPR_GAMING: {
      int ey = 32 + breatheY;
      // Intensity pulse on hit events (fast sine)
      int gPulse = (int)(abs(sin(now / 120.0f)) * 2.0f);
      drawEye(40, ey, 40 + gPulse, 32 + gPulse, 12, px, py, 5, 0, 0);
      drawEye(88, ey, 40 + gPulse, 32 + gPulse, 12, px, py, 5, 0, 0);
      drawSparkle(14, 50);
      drawSparkle(114, 50);
      // Crosshair dot at top
      oled.setDrawColor(1);
      oled.drawDisc(64, 8, 2);
      oled.drawHLine(60, 8, 3);
      oled.drawHLine(66, 8, 3);
      oled.drawVLine(64, 4, 3);
      oled.drawVLine(64, 10, 3);
      break;
    }

    // ── WATCHING: wide cinematic eyes, moving dot tracking ────────────────
    case EXPR_WATCHING: {
      int ey = 32 + breatheY;
      // Eyes track a slow moving point (simulates following screen)
      int tpx = (int)(sin(now / 2000.0f) * 8.0f);
      drawEye(40, ey, 44, 34, 13, tpx, 0, 6, 0, 0);
      drawEye(88, ey, 44, 34, 13, tpx, 0, 6, 0, 0);
      // Play triangle icon bottom-right
      oled.setDrawColor(1);
      oled.drawLine(110, 46, 110, 56);
      oled.drawLine(110, 46, 120, 51);
      oled.drawLine(110, 56, 120, 51);
      break;
    }

    // ── TYPING: downcast eyes, pulsing dots ────────────────────────────────
    case EXPR_TYPING: {
      int ey = 31 + breatheY;
      drawEye(40, ey, 36, 26, 9, px, py + 3, 6, 0, 0);
      drawEye(88, ey, 36, 26, 9, px, py + 3, 6, 0, 0);
      // Animated typing ellipsis
      int dotPhase = (int)(now / 350) % 4;
      oled.setFont(u8g2_font_6x10_tf);
      oled.setDrawColor(1);
      oled.drawStr(46, 58, dotPhase > 0 ? (dotPhase > 1 ? (dotPhase > 2 ? "..." : "..") : ".") : " ");
      break;
    }

    // ── AUTONOMOUS: pupils drift in figure-8 Lissajous ────────────────────
    case EXPR_AUTONOMOUS: {
      int ey = 32 + breatheY;
      int apx = (int)(sin(now / 1300.0f) * 6.0f);
      int apy = (int)(sin(now / 650.0f) * 3.0f);
      drawEye(40, ey, 36, 28, 10, apx, apy, 7, 0, 0);
      drawEye(88, ey, 36, 28, 10, apx, apy, 7, 0, 0);
      // Subtle AI indicator dot top-right
      oled.setDrawColor(1);
      if ((now / 800) % 2 == 0) oled.drawDisc(122, 6, 2);
      break;
    }

    // ── TALKING: waveform mouth, animated pupils ────────────────────────────
    case EXPR_TALKING: {
      // Pupils shift rhythmically as if following speech
      float sp = now / 350.0f;
      int tpx = (int)(sin(sp) * 3.0f);
      int tpy = (int)(cos(sp * 0.7f) * 2.0f) + breatheY;
      drawEye(40, 32 + tpy, 36, 28, 10, tpx, 0, 7, 0, 0);
      drawEye(88, 32 + tpy, 36, 28, 10, tpx, 0, 7, 0, 0);
      drawWaveformMouth(now);
      // Small mic icon top-left
      oled.setDrawColor(1);
      oled.drawRBox(4, 6, 6, 10, 2);
      oled.drawLine(2, 16, 10, 16);
      oled.drawVLine(6, 16, 3);
      break;
    }

    // ── ALARMED: wide shocked eyes, pulsing alert frame ────────────────────
    case EXPR_ALARMED: {
      // Eyes dilate on the pulse beat
      bool flashOn = ((now / 250) % 2) == 0;
      int eyeR = flashOn ? 15 : 12;
      int ey = 32 + breatheY + (flashOn ? -1 : 0);
      drawEye(40, ey, 44, 36, eyeR, px / 3, py / 3, 3, 0, 0);
      drawEye(88, ey, 44, 36, eyeR, px / 3, py / 3, 3, 0, 0);
      drawBrows(40, ey, false, true);
      drawBrows(88, ey, false, true);
      drawAlertFrame(now);
      break;
    }

    // ── DEEP_SLEEP: dim cascading Zs ───────────────────────────────────────
    case EXPR_DEEP_SLEEP: {
      int zOff = (int)(now / 900) % 14;
      oled.setFont(u8g2_font_10x20_tf);
      oled.setDrawColor(1);
      oled.drawStr(36, 28 - zOff / 3, "Z");
      oled.setFont(u8g2_font_6x10_tf);
      oled.drawStr(56, 40 - zOff / 4, "z");
      oled.drawStr(70, 50 - zOff / 5, "z");
      break;
    }

    // ── RELAXED: default calm, fully wired to breathing ────────────────────
    case EXPR_RELAXED:
    default: {
      int ey = 32 + breatheY + musicBounce;
      drawEye(40, ey, 36, 28, 10, px, py, 7, 0, 0);
      drawEye(88, ey, 36, 28, 10, px, py, 7, 0, 0);
      break;
    }
  }

  drawStatusLabel();
  oled.sendBuffer();
}

// ----------------------------------------------------------------------------
// TFT dashboard
// ----------------------------------------------------------------------------
void printTrunc(const char* text, int maxChars) {
  if (text == nullptr) return;
  for (int i = 0; text[i] != '\0' && i < maxChars; i++) {
    tft.write((uint8_t)text[i]);
  }
}

void formatTime(int seconds, char* buffer, size_t size) {
  if (seconds < 0) seconds = 0;
  snprintf(buffer, size, "%d:%02d", seconds / 60, seconds % 60);
}


// drawTft() and updateBacklight() are provided by ui_modern.h

// ----------------------------------------------------------------------------
// Voice assistant (Wi-Fi HTTP + MAX98357A I2S output)
// ----------------------------------------------------------------------------
// MAX98357A wiring (not populated in the base build):
//   VIN -> 5V, GND -> GND, SD -> 3.3V (or leave floating if the board pulls up)
//   BCLK -> GPIO40, LRC -> GPIO41, DIN -> GPIO42
//   Speaker -> amplifier +/-
// The existing GPIO21 PWM speaker is still used for local beeps.
//
// Configure Wi-Fi and the backend URL either in voice_config.h (compile-time)
// or over serial (stored in NVS):
//   {"cmd":"wifi","payload":{"ssid":"...","pass":"..."}}
//   {"cmd":"voice_server","payload":{"url":"http://192.168.1.50:8080"}}
//   {"cmd":"voice","payload":{"action":"start"}}
// The backend must listen on 0.0.0.0:8080 and the PC firewall must allow the
// device to reach it. Audio never leaves the local network except for the
// Nemotron API and edge-tts, which the PC backend calls.

#define VOICE_SAMPLE_RATE       16000
#define VOICE_MAX_SECONDS       6
#define VOICE_MAX_SAMPLES       (VOICE_SAMPLE_RATE * VOICE_MAX_SECONDS)
#define VOICE_MAX_PCM_BYTES     (VOICE_MAX_SAMPLES * 2)
#define VOICE_WIFI_TIMEOUT_MS   15000UL
#define VOICE_WIFI_IDLE_MS      120000UL
#define VOICE_HTTP_TIMEOUT_MS   60000

#ifndef VOICE_WIFI_ALWAYS_ON
#define VOICE_WIFI_ALWAYS_ON    0
#endif
#ifndef VOICE_WIFI_SSID
#define VOICE_WIFI_SSID         ""
#endif
#ifndef VOICE_WIFI_PASS
#define VOICE_WIFI_PASS         ""
#endif
#ifndef VOICE_SERVER_URL
#define VOICE_SERVER_URL        ""
#endif

enum VoiceState {
  VOICE_IDLE,
  VOICE_CONNECTING,
  VOICE_LISTENING,
  VOICE_UPLOADING,
  VOICE_THINKING,
  VOICE_SPEAKING,
  VOICE_ERROR
};

Preferences voicePrefs;

VoiceState voiceState = VOICE_IDLE;
bool voiceOverlayActive = false;
unsigned long voiceOverlayUntil = 0;
unsigned long voiceRecordStart = 0;
unsigned long voiceWifiIdleAt = 0;
bool voiceWifiConnected = false;

uint8_t* voicePcm = nullptr;
size_t voicePcmLen = 0;
uint8_t* voiceWav = nullptr;
size_t voiceWavLen = 0;
uint8_t* voiceReplyWav = nullptr;
size_t voiceReplyLen = 0;

char voiceTranscript[192] = "";
char voiceReplyText[384] = "";
char voiceWifiSsid[64] = "";
char voiceWifiPass[64] = "";
char voiceServerUrl[160] = "";

const char* voiceStateName() {
  switch (voiceState) {
    case VOICE_CONNECTING: return "connecting";
    case VOICE_LISTENING:  return "listening";
    case VOICE_UPLOADING:  return "uploading";
    case VOICE_THINKING:   return "thinking";
    case VOICE_SPEAKING:   return "speaking";
    case VOICE_ERROR:      return "error";
    default:               return "idle";
  }
}

bool voiceIsCapturing() {
  return voiceState == VOICE_LISTENING;
}

static void voiceCopy(char* dst, size_t dstSize, const char* src) {
  if (!dst || dstSize == 0) return;
  if (!src) {
    dst[0] = '\0';
    return;
  }
  strncpy(dst, src, dstSize - 1);
  dst[dstSize - 1] = '\0';
}

void voiceLoadConfig() {
  voiceWifiSsid[0] = '\0';
  voiceWifiPass[0] = '\0';
  voiceServerUrl[0] = '\0';

  voicePrefs.begin("voice", true);
  String ssid = voicePrefs.getString("ssid", "");
  String pass = voicePrefs.getString("pass", "");
  String url = voicePrefs.getString("url", "");
  voicePrefs.end();

  if (ssid.length()) voiceCopy(voiceWifiSsid, sizeof(voiceWifiSsid), ssid.c_str());
  if (pass.length()) voiceCopy(voiceWifiPass, sizeof(voiceWifiPass), pass.c_str());
  if (url.length()) voiceCopy(voiceServerUrl, sizeof(voiceServerUrl), url.c_str());

  if (voiceWifiSsid[0] == '\0' && strlen(VOICE_WIFI_SSID) > 0) {
    voiceCopy(voiceWifiSsid, sizeof(voiceWifiSsid), VOICE_WIFI_SSID);
  }
  if (voiceWifiPass[0] == '\0' && strlen(VOICE_WIFI_PASS) > 0) {
    voiceCopy(voiceWifiPass, sizeof(voiceWifiPass), VOICE_WIFI_PASS);
  }
  if (voiceServerUrl[0] == '\0' && strlen(VOICE_SERVER_URL) > 0) {
    voiceCopy(voiceServerUrl, sizeof(voiceServerUrl), VOICE_SERVER_URL);
  }
}

void voiceSaveConfig(const char* ssid, const char* pass, const char* url) {
  voicePrefs.begin("voice", false);
  if (ssid && ssid[0]) voicePrefs.putString("ssid", ssid);
  if (pass && pass[0]) voicePrefs.putString("pass", pass);
  if (url && url[0]) voicePrefs.putString("url", url);
  voicePrefs.end();

  voiceLoadConfig();
  Serial.printf("[voice] config ssid=%s url=%s\n",
                voiceWifiSsid[0] ? voiceWifiSsid : "(unset)",
                voiceServerUrl[0] ? voiceServerUrl : "(unset)");
}

static void voiceUrlDecode(const String& src, char* dst, size_t dstSize) {
  if (!dst || dstSize == 0) return;
  size_t j = 0;
  for (size_t i = 0; i < src.length() && j + 1 < dstSize; i++) {
    char c = src[i];
    if (c == '%' && i + 2 < src.length()) {
      char hex[3] = { src[i + 1], src[i + 2], 0 };
      c = (char)strtol(hex, nullptr, 16);
      i += 2;
    } else if (c == '+') {
      c = ' ';
    }
    if ((unsigned char)c >= 128) c = '?';
    dst[j++] = c;
  }
  dst[j] = '\0';
}

static int voiceDrawWrapped(const char* text, int x, int y, int maxLines) {
  if (!text || !text[0]) return y;
  char line[24];
  int lineLen = 0;
  int lines = 0;
  const char* p = text;
  while (*p && lines < maxLines) {
    while (*p == ' ') p++;
    if (!*p) break;
    const char* word = p;
    while (*p && *p != ' ') p++;
    int wordLen = (int)(p - word);
    if (wordLen > 20) wordLen = 20;
    if (lineLen > 0 && lineLen + 1 + wordLen > 20) {
      line[lineLen] = '\0';
      oled.drawStr(x, y, line);
      y += 9;
      lines++;
      lineLen = 0;
      if (lines >= maxLines) break;
    }
    if (lineLen > 0) line[lineLen++] = ' ';
    for (int i = 0; i < wordLen && lineLen < 20; i++) {
      char c = word[i];
      if ((unsigned char)c >= 128) c = '?';
      line[lineLen++] = c;
    }
  }
  if (lineLen > 0 && lines < maxLines) {
    line[lineLen] = '\0';
    oled.drawStr(x, y, line);
    y += 9;
  }
  return y;
}

void drawVoiceOverlay(unsigned long now) {
  oled.clearBuffer();
  oled.setFont(u8g2_font_6x10_tf);

  const char* title = "Omnipect";
  switch (voiceState) {
    case VOICE_CONNECTING: title = "Connecting"; break;
    case VOICE_LISTENING:  title = "Listening"; break;
    case VOICE_UPLOADING:  title = "Uploading"; break;
    case VOICE_THINKING:   title = "Thinking"; break;
    case VOICE_SPEAKING:   title = "Speaking"; break;
    case VOICE_ERROR:      title = "Voice error"; break;
    default:               title = "Omnipect"; break;
  }
  oled.drawStr(2, 10, title);

  if (voiceState == VOICE_LISTENING) {
    unsigned long elapsed = now - voiceRecordStart;
    int width = (int)((elapsed * 120UL) / (VOICE_MAX_SECONDS * 1000UL));
    if (width < 0) width = 0;
    if (width > 120) width = 120;
    oled.drawFrame(2, 14, 124, 6);
    if (width > 0) oled.drawBox(3, 15, width, 4);
  }

  oled.setFont(u8g2_font_5x7_tf);
  int y = 32;
  if (voiceState == VOICE_LISTENING) {
    voiceDrawWrapped("Speak now. Press VOICE to stop.", 2, y, 3);
  } else if (voiceState == VOICE_CONNECTING) {
    voiceDrawWrapped(voiceWifiSsid[0] ? voiceWifiSsid : "No Wi-Fi configured", 2, y, 3);
  } else if (voiceState == VOICE_UPLOADING || voiceState == VOICE_THINKING) {
    voiceDrawWrapped(voiceTranscript[0] ? voiceTranscript : "Processing...", 2, y, 3);
  } else {
    voiceDrawWrapped(voiceReplyText[0] ? voiceReplyText : "Ready", 2, y, 3);
  }

  oled.sendBuffer();
}

void voiceSetError(const char* message) {
  voiceCopy(voiceReplyText, sizeof(voiceReplyText), message ? message : "Voice error");
  voiceState = VOICE_ERROR;
  voiceOverlayActive = true;
  voiceOverlayUntil = millis() + 8000;
  targetExpr = EXPR_SAD;
  triggerWake(3000);
  tftDirty = true;

  if (voiceWav) {
    free(voiceWav);
    voiceWav = nullptr;
  }
  voiceWavLen = 0;
  if (voiceReplyWav) {
    free(voiceReplyWav);
    voiceReplyWav = nullptr;
  }
  voiceReplyLen = 0;

  Serial.printf("[voice] error: %s\n", voiceReplyText);
  drawVoiceOverlay(millis());
}

static inline int16_t voiceSampleToPcm16(int32_t sample) {
  // The INMP441 delivers a 24-bit sample left-justified in a 32-bit slot.
  int32_t value = sample >> 16;
  if (value > 32767) value = 32767;
  if (value < -32768) value = -32768;
  return (int16_t)value;
}

void voiceNormalizePcm() {
  if (!voicePcm || voicePcmLen < 2) return;
  int16_t* samples = (int16_t*)voicePcm;
  size_t count = voicePcmLen / 2;
  int32_t peak = 0;
  for (size_t i = 0; i < count; i++) {
    int32_t v = samples[i];
    if (v < 0) v = -v;
    if (v > peak) peak = v;
  }
  if (peak < 200) return;
  float gain = 24000.0f / (float)peak;
  if (gain > 8.0f) gain = 8.0f;
  if (gain <= 1.01f) return;
  for (size_t i = 0; i < count; i++) {
    int32_t v = (int32_t)((float)samples[i] * gain);
    if (v > 32767) v = 32767;
    if (v < -32768) v = -32768;
    samples[i] = (int16_t)v;
  }
}

bool voiceBuildWav() {
  if (voiceWav) {
    free(voiceWav);
    voiceWav = nullptr;
  }
  voiceWavLen = 44 + voicePcmLen;
  voiceWav = (uint8_t*)ps_malloc(voiceWavLen);
  if (!voiceWav) {
    voiceSetError("Out of PSRAM for WAV");
    return false;
  }

  uint8_t* h = voiceWav;
  uint32_t dataLen = (uint32_t)voicePcmLen;
  uint32_t fileLen = 36 + dataLen;
  uint32_t byteRate = (uint32_t)VOICE_SAMPLE_RATE * 2;
  uint32_t sampleRate = (uint32_t)VOICE_SAMPLE_RATE;
  uint32_t fmtLen = 16;
  uint16_t audioFormat = 1;
  uint16_t channels = 1;
  uint16_t blockAlign = 2;
  uint16_t bitsPerSample = 16;

  memcpy(h + 0, "RIFF", 4);
  memcpy(h + 4, &fileLen, 4);
  memcpy(h + 8, "WAVE", 4);
  memcpy(h + 12, "fmt ", 4);
  memcpy(h + 16, &fmtLen, 4);
  memcpy(h + 20, &audioFormat, 2);
  memcpy(h + 22, &channels, 2);
  memcpy(h + 24, &sampleRate, 4);
  memcpy(h + 28, &byteRate, 4);
  memcpy(h + 32, &blockAlign, 2);
  memcpy(h + 34, &bitsPerSample, 2);
  memcpy(h + 36, "data", 4);
  memcpy(h + 40, &dataLen, 4);
  memcpy(h + 44, voicePcm, voicePcmLen);
  return true;
}

void voiceSendStatus() {
  txDoc.clear();
  txDoc["type"] = "voice_status";
  txDoc["state"] = voiceStateName();
  txDoc["wifi"] = (WiFi.status() == WL_CONNECTED);
  txDoc["ip"] = WiFi.localIP().toString();
  txDoc["ssid"] = voiceWifiSsid;
  txDoc["server"] = voiceServerUrl;
  txDoc["heap"] = ESP.getFreeHeap();
  txDoc["psram"] = ESP.getFreePsram();
  sendTx(txDoc);
}

bool voiceEnsureWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    voiceWifiConnected = true;
    voiceWifiIdleAt = millis() + VOICE_WIFI_IDLE_MS;
    return true;
  }
  if (!voiceWifiSsid[0]) {
    Serial.println("[voice] no Wi-Fi SSID configured");
    return false;
  }
  if (!voiceServerUrl[0]) {
    Serial.println("[voice] no voice server URL configured");
    return false;
  }

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(voiceWifiSsid, voiceWifiPass);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < VOICE_WIFI_TIMEOUT_MS) {
    delay(100);
    if ((millis() - start) % 500 < 100) drawVoiceOverlay(millis());
  }

  voiceWifiConnected = (WiFi.status() == WL_CONNECTED);
  if (!voiceWifiConnected) {
    Serial.println("[voice] Wi-Fi connect failed");
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    return false;
  }

  voiceWifiIdleAt = millis() + VOICE_WIFI_IDLE_MS;
  Serial.printf("[voice] Wi-Fi connected, IP=%s\n", WiFi.localIP().toString().c_str());
  return true;
}

bool voiceStartCapture() {
  if (voiceState == VOICE_LISTENING) return true;
  if (voiceState != VOICE_IDLE && voiceState != VOICE_ERROR) return false;
  if (!sensors.micOk) {
    voiceSetError("Microphone unavailable");
    return false;
  }

  voiceState = VOICE_CONNECTING;
  voiceOverlayActive = true;
  voiceOverlayUntil = millis() + 60000;
  voiceTranscript[0] = '\0';
  voiceReplyText[0] = '\0';
  drawVoiceOverlay(millis());

  if (!voiceEnsureWifi()) {
    voiceSetError("Wi-Fi connection failed");
    return false;
  }

  if (!voicePcm) {
    voicePcm = (uint8_t*)ps_malloc(VOICE_MAX_PCM_BYTES);
    if (!voicePcm) {
      voiceSetError("Out of PSRAM for recording");
      return false;
    }
  }

  voicePcmLen = 0;
  voiceRecordStart = millis();
  voiceState = VOICE_LISTENING;
  targetExpr = EXPR_TALKING;
  triggerWake((unsigned long)VOICE_MAX_SECONDS * 1000UL + 5000UL);
  beep(1400, 60);
  tftDirty = true;
  Serial.println("[voice] listening");
  drawVoiceOverlay(millis());
  return true;
}

void voiceSendToBackend() {
  if (!voiceWav || voiceWavLen < 44) {
    voiceSetError("No recorded audio");
    return;
  }
  if (!voiceServerUrl[0]) {
    voiceSetError("No voice server URL");
    return;
  }

  String url = String(voiceServerUrl);
  if (!url.endsWith("/api/v1/voice/chat")) {
    if (url.endsWith("/")) url.remove(url.length() - 1);
    url += "/api/v1/voice/chat";
  }
  if (url.indexOf('?') < 0) {
    url += "?session_id=omnipect&language=en";
  }

  HTTPClient http;
  http.setTimeout(VOICE_HTTP_TIMEOUT_MS);
  if (!http.begin(url)) {
    voiceSetError("HTTP begin failed");
    return;
  }
  const char* headerKeys[] = {"X-Transcript", "X-Reply-Text"};
  http.collectHeaders(headerKeys, 2);
  http.addHeader("Content-Type", "audio/wav");
  http.addHeader("X-Session-Id", "omnipect");
  http.addHeader("X-Device", "esp32s3");

  int code = http.POST(voiceWav, voiceWavLen);
  if (code != 200) {
    char message[48];
    snprintf(message, sizeof(message), "HTTP %d", code);
    http.end();
    voiceSetError(message);
    return;
  }

  String transcript = http.header("X-Transcript");
  String reply = http.header("X-Reply-Text");
  voiceUrlDecode(transcript, voiceTranscript, sizeof(voiceTranscript));
  voiceUrlDecode(reply, voiceReplyText, sizeof(voiceReplyText));

  int contentLength = http.getSize();
  if (voiceReplyWav) {
    free(voiceReplyWav);
    voiceReplyWav = nullptr;
  }
  voiceReplyLen = 0;

  if (contentLength > 44 || contentLength < 0) {
    size_t cap = (contentLength > 44) ? (size_t)contentLength : (512U * 1024U);
    voiceReplyWav = (uint8_t*)ps_malloc(cap);
    if (voiceReplyWav) {
      WiFiClient* stream = http.getStreamPtr();
      size_t read = 0;
      unsigned long lastData = millis();
      while ((contentLength < 0 || read < (size_t)contentLength) &&
             read < cap &&
             (millis() - lastData) < 20000UL) {
        size_t available = (size_t)stream->available();
        if (available > 0) {
          size_t want = available;
          if (want > cap - read) want = cap - read;
          size_t got = stream->readBytes((char*)(voiceReplyWav + read), want);
          if (got > 0) {
            read += got;
            lastData = millis();
          }
        } else {
          if (contentLength < 0 && !http.connected()) break;
          readSerial();
          delay(5);
        }
      }
      voiceReplyLen = read;
    }
  }
  http.end();

  if (voiceWav) {
    free(voiceWav);
    voiceWav = nullptr;
  }
  voiceWavLen = 0;

  Serial.printf("[voice] reply: %s\n", voiceReplyText);
  Serial.printf("[voice] audio: %u bytes\n", (unsigned)voiceReplyLen);

  if (voiceReplyLen > 44) {
    voiceState = VOICE_SPEAKING;
    voiceOverlayUntil = millis() + 60000;
    drawVoiceOverlay(millis());
    beep(1600, 40);
    audioOut.playWAV(voiceReplyWav, voiceReplyLen);
  }

  voiceState = VOICE_IDLE;
  voiceOverlayActive = true;
  voiceOverlayUntil = millis() + 8000;
  targetExpr = EXPR_HAPPY;
  triggerWake(8000);
  tftDirty = true;
  drawVoiceOverlay(millis());
}

void voiceFinishCapture() {
  if (voiceState != VOICE_LISTENING) return;

  voiceState = VOICE_UPLOADING;
  voiceOverlayActive = true;
  voiceOverlayUntil = millis() + 60000;
  targetExpr = EXPR_THINKING;
  triggerWake(60000);
  tftDirty = true;

  voiceNormalizePcm();
  Serial.printf("[voice] captured %u bytes (%.2fs)\n",
                (unsigned)voicePcmLen,
                voicePcmLen / (float)(VOICE_SAMPLE_RATE * 2));

  if (voicePcmLen < 3200) {
    voiceSetError("No audio captured");
    return;
  }
  if (!voiceBuildWav()) return;

  Serial.printf("[voice] uploading %u bytes\n", (unsigned)voiceWavLen);
  voiceState = VOICE_THINKING;
  drawVoiceOverlay(millis());
  voiceSendToBackend();
}

void voiceCaptureTick() {
  if (voiceState != VOICE_LISTENING) return;

  unsigned long elapsed = millis() - voiceRecordStart;
  if (elapsed >= (unsigned long)VOICE_MAX_SECONDS * 1000UL) {
    voiceFinishCapture();
    return;
  }

  size_t targetSamples = (size_t)((uint64_t)elapsed * VOICE_SAMPLE_RATE / 1000ULL);
  size_t targetBytes = targetSamples * 2;
  if (targetBytes > VOICE_MAX_PCM_BYTES) targetBytes = VOICE_MAX_PCM_BYTES;
  if (voicePcmLen >= targetBytes) return;

  int32_t chunk[128];
  while (voicePcmLen < targetBytes && voicePcmLen + 2 <= VOICE_MAX_PCM_BYTES) {
    size_t wantBytes = (targetBytes - voicePcmLen) * 2;
    if (wantBytes > sizeof(chunk)) wantBytes = sizeof(chunk);
    size_t got = i2s.readBytes((char*)chunk, wantBytes);
    if (got == 0) break;
    size_t samples = got / sizeof(int32_t);
    for (size_t i = 0; i < samples && voicePcmLen + 2 <= VOICE_MAX_PCM_BYTES; i++) {
      int16_t value = voiceSampleToPcm16(chunk[i]);
      memcpy(voicePcm + voicePcmLen, &value, 2);
      voicePcmLen += 2;
    }
  }
}

void voiceCancel() {
  if (voicePcm) {
    free(voicePcm);
    voicePcm = nullptr;
  }
  if (voiceWav) {
    free(voiceWav);
    voiceWav = nullptr;
  }
  if (voiceReplyWav) {
    free(voiceReplyWav);
    voiceReplyWav = nullptr;
  }
  voicePcmLen = 0;
  voiceWavLen = 0;
  voiceReplyLen = 0;
  voiceState = VOICE_IDLE;
  voiceOverlayActive = false;
  targetExpr = EXPR_CURIOUS;
  tftDirty = true;
  Serial.println("[voice] cancelled");
}

void voiceToggle() {
  if (voiceState == VOICE_LISTENING) {
    voiceFinishCapture();
  } else if (voiceState == VOICE_IDLE || voiceState == VOICE_ERROR) {
    voiceStartCapture();
  }
}

void voiceTick(unsigned long now) {
  if (voiceState == VOICE_LISTENING) {
    voiceCaptureTick();
  }

  if (voiceOverlayActive && now > voiceOverlayUntil) {
    voiceOverlayActive = false;
    if (voiceState == VOICE_ERROR) voiceState = VOICE_IDLE;
    tftDirty = true;
  }

#if !VOICE_WIFI_ALWAYS_ON
  if (voiceWifiConnected && voiceState == VOICE_IDLE &&
      voiceWifiIdleAt && now > voiceWifiIdleAt) {
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    voiceWifiConnected = false;
    voiceWifiIdleAt = 0;
    Serial.println("[voice] Wi-Fi idle, radio off");
  }
#endif
}

void voiceHandleCommand(JsonObjectConst payload) {
  const char* action = payload["action"] | "";
  if (strcmp(action, "start") == 0) {
    voiceStartCapture();
  } else if (strcmp(action, "stop") == 0) {
    if (voiceState == VOICE_LISTENING) voiceFinishCapture();
  } else if (strcmp(action, "cancel") == 0) {
    voiceCancel();
  } else if (strcmp(action, "status") == 0) {
    voiceSendStatus();
  } else if (strcmp(action, "config") == 0) {
    const char* ssid = payload["ssid"] | "";
    const char* pass = payload["pass"] | "";
    const char* url = payload["url"] | "";
    voiceSaveConfig(ssid[0] ? ssid : nullptr,
                    pass[0] ? pass : nullptr,
                    url[0] ? url : nullptr);
    WiFi.disconnect(true);
  } else {
    Serial.printf("[voice] unknown action: %s\n", action);
  }
}

void voiceInit() {
  voiceLoadConfig();

  audioOut.setPins(PIN_AMP_BCLK, PIN_AMP_LRC, PIN_AMP_DIN, -1, -1);
  if (audioOut.begin(I2S_MODE_STD, VOICE_SAMPLE_RATE,
                     I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO)) {
    audioOutReady = true;
    Serial.println("[voice] I2S TX ready (BCLK=40, LRC=41, DIN=42)");
  } else {
    audioOutReady = false;
    Serial.println("[voice] I2S TX init failed (MAX98357A not wired yet?)");
  }

  Serial.printf("[voice] ssid=%s server=%s\n",
                voiceWifiSsid[0] ? voiceWifiSsid : "(unset)",
                voiceServerUrl[0] ? voiceServerUrl : "(unset)");

#if VOICE_WIFI_ALWAYS_ON
  if (voiceWifiSsid[0]) {
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    WiFi.begin(voiceWifiSsid, voiceWifiPass);
    voiceWifiIdleAt = millis() + VOICE_WIFI_IDLE_MS;
  }
#endif
}

// ----------------------------------------------------------------------------
// Arduino entry points
// ----------------------------------------------------------------------------
void setup() {
  Serial.setRxBufferSize(16384);
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("=== Omnipect boot ===");
  Serial.printf("reset_reason=%d psram=%d heap=%u\n",
                (int)esp_reset_reason(), (int)psramFound(),
                (unsigned)ESP.getFreeHeap());
  Serial.flush();

  // Allocate cover art and blurred background buffers
  if (psramFound()) {
    coverThumb = (uint16_t*)ps_malloc(COVER_THUMB_W * COVER_THUMB_H * sizeof(uint16_t));
    lyricsBg = (uint16_t*)ps_malloc(TFT_W * TFT_H * sizeof(uint16_t));
    Serial.printf("[boot] PSRAM buffers: thumb=%p, lyricsBg=%p\n", coverThumb, lyricsBg);
  } else {
    coverThumb = (uint16_t*)malloc(COVER_THUMB_W * COVER_THUMB_H * sizeof(uint16_t));
    lyricsBg = (uint16_t*)malloc(TFT_W * TFT_H * sizeof(uint16_t));
    Serial.printf("[boot] Heap buffers: thumb=%p, lyricsBg=%p\n", coverThumb, lyricsBg);
  }

  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  Wire.setClock(100000);

  Serial.println("[boot] Scanning I2C bus...");
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      Serial.printf("[boot] Found I2C device at 0x%02X\n", a);
    }
  }
  Serial.flush();

  Serial.println("[boot] buttons"); Serial.flush();
  initButtons();
  resetButtonMap();
  Serial.println("[boot] oled"); Serial.flush();
  initOled();
  Serial.println("[boot] tft"); Serial.flush();
  initTft();
#if defined(HAS_U8G2_GFX)
  u8g2gfx.begin(sprite);
  u8g2gfx.setFontMode(1); // transparent
#endif
  Serial.println("[boot] sensors"); Serial.flush();
  initSensors();
  Serial.println("[boot] mic"); Serial.flush();
  initMic();
  Serial.println("[boot] voice"); Serial.flush();
  voiceInit();
  Serial.println("[boot] led"); Serial.flush();
  ledInit();
  Serial.println("[boot] init done"); Serial.flush();

  randomSeed(micros());

  state.backendOnline = false;
  state.stateReceived = false;
  state.lastStateMs = 0;
  state.backendBatteryPct = -1;
  state.backendBatteryChg = -1;
  state.clockText[0] = '\0';
  state.dateText[0] = '\0';
  state.dowText[0] = '\0';
  state.expression[0] = '\0';

  pomodoro.running = false;
  pomodoro.isBreak = false;
  pomodoro.remaining = POMODORO_WORK_SECONDS;
  pomodoro.session = 0;
  pomodoro.lastTick = millis();

  Serial.println("[boot] bootScreen"); Serial.flush();
  bootScreen();
  Serial.println("[boot] bootScreen done"); Serial.flush();

  lastMotionReadMs = millis();
  lastEnvReadMs = millis();
  lastBatteryReadMs = millis();
  lastMicReadMs = millis();
  lastButtonMs = millis();
  lastPomodoroMs = millis();
  lastEyeMs = millis();
  lastTftMs = millis();
  lastHeartbeatMs = millis();
  lastSensorSendMs = millis();
  lastMotionMs = millis();
  nextBlinkMs = millis() + 2500;
  nextAutonomousMs = millis() + 12000;

  tftDirty = true;
  Serial.println("[boot] setPage"); Serial.flush();
  setPage(PAGE_HOME);
  Serial.println("[boot] setPage done"); Serial.flush();
  Serial.println("[boot] beep"); Serial.flush();
  beep(1200, 60);
  Serial.println("[boot] beep done"); Serial.flush();

  txDoc.clear();
  txDoc["type"] = "status";
  txDoc["firmware"] = FW_VERSION;
  txDoc["page"] = pageName(page);
  txDoc["mode"] = modeName();
  txDoc["bme"] = sensors.bmeOk;
  txDoc["adxl"] = sensors.adxlOk;
  txDoc["mic"] = sensors.micOk;
  sendTx(txDoc);
  Serial.println("[boot] setup complete");
  Serial.flush();
}

void loop() {
  unsigned long now = millis();

  readSerial();
  cloudTick();
  voiceTick(now);

  if (!voiceIsCapturing()) {
    if (now - lastMotionReadMs >= MOTION_MS) {
      readMotion();
      lastMotionReadMs = now;
    }

    if (now - lastEnvReadMs >= ENV_MS) {
      readEnvironment();
      lastEnvReadMs = now;
    }
  }

  if (now - lastBatteryReadMs >= BATTERY_MS) {
    updateBattery();
    lastBatteryReadMs = now;
  }

  if (now - lastMicReadMs >= MIC_MS) {
    if (!voiceIsCapturing()) readMicrophone();
    lastMicReadMs = now;
  }

  if (now - lastButtonMs >= BUTTON_MS) {
    checkButtons();
    lastButtonMs = now;
  }

  if (now - lastPomodoroMs >= POMODORO_MS) {
    updatePomodoro();
    lastPomodoroMs = now;
  }

  updateConnectivity(now);
  updateExpression(now);

  if (now - lastEyeMs >= EYE_FRAME_MS) {
    if (voiceOverlayActive) drawVoiceOverlay(now);
    else drawEyes(now);
    lastEyeMs = now;
  }

  if (!voiceIsCapturing() && (tftDirty || now - lastTftMs >= TFT_REFRESH_MS)) {
    drawTft(now);
    tftDirty = false;
    // advance on a fixed grid so heavy frames don't permanently drag the
    // frame rate down; resync only if we fell more than one period behind
    lastTftMs += TFT_REFRESH_MS;
    if ((long)(now - lastTftMs) > (long)TFT_REFRESH_MS) lastTftMs = now;
  }

  if (now - lastHeartbeatMs >= HEARTBEAT_MS) {
    sendHeartbeat();
    lastHeartbeatMs = now;
  }

  if (now - lastSensorSendMs >= SENSOR_SEND_MS) {
    sendSensorData();
    lastSensorSendMs = now;
  }

  if (noticeOverride && now >= noticeUntil) {
    noticeOverride = false;
    page = pageBeforeNotice;
    tftDirty = true;
    sendHeartbeat();
  }

  if (inspectCapturing && inspectCount < INSPECT_SAMPLES) {
    if (millis() - inspectStartMs >= (unsigned long)(inspectCount * 25)) {
      inspectX[inspectCount] = sensors.accelX;
      inspectY[inspectCount] = sensors.accelY;
      inspectZ[inspectCount] = sensors.accelZ;
      inspectCount++;
      tftDirty = true;
      if (inspectCount >= INSPECT_SAMPLES) {
        // Capture complete - send to backend
        inspectCapturing = false;
        sendInspectionData();
        tftDirty = true;
        tftFullRedraw = true;
      }
    }
  }


  // Optional addressable LED strip update (no-op if unavailable/disabled).
  ledUpdate(now);
}