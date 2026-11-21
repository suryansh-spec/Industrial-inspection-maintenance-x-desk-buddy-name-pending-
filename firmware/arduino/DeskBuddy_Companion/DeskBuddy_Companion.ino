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
// Serial protocol (112000 baud, newline-delimited JSON)
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
#include <U8g2lib.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <Adafruit_BME280.h>
#include <Adafruit_ADXL345_U.h>
#include <ESP_I2S.h>
#include <ArduinoJson.h>
#include <math.h>

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

#define PIN_SPEAKER       21
#define PIN_BATTERY       1

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
const unsigned long TFT_REFRESH_MS   = 1000;
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
  MODE_DESK_BUDDY,
  MODE_INSPECTION
};

enum ScreenPage {
  PAGE_HOME,
  PAGE_MUSIC,
  PAGE_LYRICS,
  PAGE_PC,
  PAGE_ENV,
  PAGE_NOTIFICATIONS,
  PAGE_POMODORO,
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
PomodoroState pomodoro;
Note notes[8];
int noteCount = 0;

DeviceMode mode = MODE_DESK_BUDDY;
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
void drawHeader(const char* title);
void drawHome();
void drawMusicPage();
void drawLyricsPage();
void drawPcPage();
void drawEnvPage();
void drawNotificationsPage();
void drawPomodoroPage();
void drawInspectionPage();
void drawBar(int x, int y, int w, int h, float percent, uint16_t color);
void drawBattery(int x, int y);
void updateBacklight(unsigned long now);
const char* activityLabel();

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
    default: return "home";
  }
}

const char* modeName() {
  return mode == MODE_INSPECTION ? "inspection" : "desk_buddy";
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
  tone(PIN_SPEAKER, frequency, durationMs);
}

void doubleBeep() {
  tone(PIN_SPEAKER, 1500, 70);
  delay(90);
  tone(PIN_SPEAKER, 1900, 90);
}

// ----------------------------------------------------------------------------
// Hardware setup
// ----------------------------------------------------------------------------
void initButtons() {
  for (int i = 0; i < 5; i++) {
    pinMode(BUTTON_PINS[i], INPUT_PULLUP);
    buttonLastRead[i] = digitalRead(BUTTON_PINS[i]) == HIGH;
    buttonStable[i] = buttonLastRead[i];
  }
}

void initOled() {
  oled.setI2CAddress(0x3C << 1);
  oled.begin();
  oled.setFont(u8g2_font_5x7_tf);
}

void initTft() {
  pinMode(PIN_TFT_BL, OUTPUT);
  analogWrite(PIN_TFT_BL, 220);
  lastBacklight = 220;

  SPI.begin(PIN_TFT_SCLK, -1, PIN_TFT_MOSI, PIN_TFT_CS);
  tft.initR(INITR_BLACKTAB);
  tft.setRotation(0);
  // Panel is BGR type: set BGR bit (0x08) keeping rotation-0 transform (0xC0).
  uint8_t madctl = 0xC8;
  tft.sendCommand(ST77XX_MADCTL, &madctl, 1);
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
  oled.drawStr(30, 61, "DeskBuddy");
  oled.sendBuffer();

  tft.fillScreen(theme.bg);
  tft.fillRect(0, 0, tft.width(), 16, theme.headerBg);
  tft.setTextColor(theme.text, theme.headerBg);
  tft.setTextSize(1);
  tft.setCursor(4, 4);
  tft.print("DESKBUDDY COMPANION");
  tft.setTextColor(theme.accent, theme.bg);
  tft.setTextSize(2);
  tft.setCursor(4, 32);
  tft.print("Hello!");
  tft.setTextColor(theme.text, theme.bg);
  tft.setTextSize(1);
  tft.setCursor(4, 60);
  tft.print("PC-aware desk buddy");
  tft.setCursor(4, 74);
  tft.print("FW ");
  tft.print(FW_VERSION);
  tft.setCursor(4, 96);
  tft.print("Starting sensors...");
  delay(1200);
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

  double sum = 0.0;
  for (size_t i = 0; i < samples; i++) {
    float sample = (float)micBuffer[i];
    sum += sample * sample;
  }

  float rms = sqrt((float)(sum / samples));
  if (rms < 1.0f) rms = 1.0f;

  // INMP441 data is a 24-bit sample left-justified in a 32-bit slot. Treat the
  // 32-bit word as full scale and map -70..-15 dBFS to a 0..100 level.
  float dbfs = 20.0f * log10f(rms / 2147483648.0f);
  float level = (dbfs + 70.0f) * (100.0f / 55.0f);
  level = constrain(level, 0.0f, 100.0f);

  if (level > micLevelSmoothed) {
    micLevelSmoothed = (micLevelSmoothed * 0.5f) + (level * 0.5f);
  } else {
    micLevelSmoothed = (micLevelSmoothed * 0.85f) + (level * 0.15f);
  }
  sensors.micLevel = (int)(micLevelSmoothed + 0.5f);
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
      if (pressed) {
        buttonPressed[i] = true;
        lastMotionMs = now;
        handleButton(i);
      } else {
        buttonPressed[i] = false;
      }
    }
  }
}

void handleButton(int index) {
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
  mode = (mode == MODE_DESK_BUDDY) ? MODE_INSPECTION : MODE_DESK_BUDDY;
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
      if (serialBuffer.length() > 0) {
        handleBackendLine(serialBuffer);
        serialBuffer = "";
      }
    } else if (c != '\r') {
      // The state packet grew with lyrics and telemetry. Allow room for
      // JSON-escaped non-ASCII text (Python escapes each character as \uXXXX)
      // and base64 cover art payloads.
      if (serialBuffer.length() < 8192) {
        serialBuffer += c;
      } else {
        serialBuffer = "";
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

  if (strcmp(cmd, "deskbuddy_state") == 0) {
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
  } else if (strcmp(cmd, "mode_switch") == 0) {
    const char* requested = payload["mode"] | "desk_buddy";
    mode = (strcmp(requested, "inspection") == 0) ? MODE_INSPECTION : MODE_DESK_BUDDY;
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
    tone(PIN_SPEAKER, frequency, duration);
  } else if (strcmp(cmd, "get_status") == 0) {
    sendHeartbeat();
  } else if (strcmp(cmd, "get_sensors") == 0) {
    sendSensorData();
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
  serializeJson(txDoc, Serial);
  Serial.println();
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

  serializeJson(txDoc, Serial);
  Serial.println();
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

  serializeJson(txDoc, Serial);
  Serial.println();
}

void sendButton(const char* button) {
  txDoc.clear();
  txDoc["type"] = "button";
  txDoc["button"] = button;
  txDoc["page"] = pageName(page);
  txDoc["mode"] = modeName();
  serializeJson(txDoc, Serial);
  Serial.println();
}

void sendMusicAction(const char* action) {
  txDoc.clear();
  txDoc["type"] = "music";
  txDoc["action"] = action;
  serializeJson(txDoc, Serial);
  Serial.println();
}

void sendPomodoroAction(const char* action) {
  txDoc.clear();
  txDoc["type"] = "pomodoro";
  txDoc["action"] = action;
  txDoc["minutes"] = POMODORO_WORK_SECONDS / 60;
  serializeJson(txDoc, Serial);
  Serial.println();
}

void sendNotificationAck(const char* id) {
  txDoc.clear();
  txDoc["type"] = "notification_ack";
  txDoc["id"] = id;
  serializeJson(txDoc, Serial);
  Serial.println();
}

void sendModeSwitched() {
  txDoc.clear();
  txDoc["type"] = "mode_switched";
  txDoc["mode"] = modeName();
  serializeJson(txDoc, Serial);
  Serial.println();
}

void sendGesture(const char* gesture) {
  txDoc.clear();
  txDoc["type"] = "gesture";
  txDoc["gesture"] = gesture;
  txDoc["page"] = pageName(page);
  txDoc["mode"] = modeName();
  serializeJson(txDoc, Serial);
  Serial.println();
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
  pageBeforeNotice = page;
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
    startPomodoro(25);
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

void drawHeader(const char* title) {
  int width = tft.width();
  tft.fillScreen(theme.bg);
  tft.fillRect(0, 0, width, 15, theme.headerBg);
  tft.setTextSize(1);
  tft.setTextColor(theme.headerText, theme.headerBg);
  tft.setCursor(4, 4);
  tft.print(title);

  uint16_t linkColor = state.backendOnline ? theme.success : theme.danger;
  tft.fillCircle(width - 8, 7, 3, linkColor);
}

void drawBar(int x, int y, int w, int h, float percent, uint16_t color) {
  tft.drawRect(x, y, w, h, theme.secondary);
  if (isnan(percent) || percent < 0.0f) return;
  int fill = (int)((constrain(percent, 0.0f, 100.0f) / 100.0f) * (w - 2));
  if (fill > 0) {
    tft.fillRect(x + 1, y + 1, fill, h - 2, color);
  }
}

void drawBattery(int x, int y) {
  int pct = batteryPercent();
  tft.drawRect(x, y, 26, 10, theme.text);
  tft.fillRect(x + 26, y + 3, 2, 4, theme.text);

  if (pct >= 0) {
    int fill = (pct * 22) / 100;
    uint16_t color = ST77XX_GREEN;
    if (pct < 20) color = ST77XX_RED;
    else if (pct < 50) color = theme.warning;
    if (fill > 0) tft.fillRect(x + 2, y + 2, fill, 6, color);
  } else if (pct == -2) {
    tft.fillRect(x + 2, y + 2, 22, 6, ST77XX_GREEN);
  }
}

// Home page partial-refresh tracking
static char lastHomeClock[8] = "";
static char lastHomeDate[32] = "";
static char lastHomeActivity[48] = "";
static char lastHomeApp[48] = "";
static char lastHomeEnv[48] = "";
static char lastHomeMusic[64] = "";
static int lastHomeBatt = -999;

void drawHome() {
  if (tftFullRedraw) {
    drawHeader("DESKBUDDY");
    lastHomeClock[0] = '\0';
    lastHomeDate[0] = '\0';
    lastHomeActivity[0] = '\0';
    lastHomeApp[0] = '\0';
    lastHomeEnv[0] = '\0';
    lastHomeMusic[0] = '\0';
    lastHomeBatt = -999;
    tftFullRedraw = false;
  }

  // Clock (size3)
  char clockBuf[8];
  snprintf(clockBuf, sizeof(clockBuf), "%s", state.clockText[0] != '\0' ? state.clockText : "--:--");
  if (strcmp(clockBuf, lastHomeClock) != 0) {
    tft.fillRect(4, 19, 120, 24, theme.bg);
    tft.setTextColor(theme.accent, theme.bg);
    tft.setTextSize(3);
    tft.setCursor(4, 19);
    tft.print(state.clockText[0] != '\0' ? state.clockText : "--:--");
    copyText(lastHomeClock, sizeof(lastHomeClock), clockBuf);
  }

  // Date line
  char dateLine[32];
  snprintf(dateLine, sizeof(dateLine), "%s %s",
           state.dateText[0] != '\0' ? state.dateText : "--",
           state.dowText);
  if (strcmp(dateLine, lastHomeDate) != 0) {
    tft.fillRect(4, 46, 120, 10, theme.bg);
    tft.setTextSize(1);
    tft.setTextColor(theme.text, theme.bg);
    tft.setCursor(4, 46);
    printTrunc(dateLine, 20);
    copyText(lastHomeDate, sizeof(lastHomeDate), dateLine);
  }

  // Activity
  const char* actLabel = activityLabel();
  if (strcmp(actLabel, lastHomeActivity) != 0) {
    tft.fillRect(4, 59, 120, 10, theme.bg);
    tft.setTextColor(theme.warning, theme.bg);
    tft.setCursor(4, 59);
    printTrunc(actLabel, 20);
    copyText(lastHomeActivity, sizeof(lastHomeActivity), actLabel);
  }

  // App name
  const char* appStr = state.appName[0] ? state.appName : "Waiting for PC...";
  if (strcmp(appStr, lastHomeApp) != 0) {
    tft.fillRect(4, 71, 120, 10, theme.bg);
    tft.setTextColor(theme.secondary, theme.bg);
    tft.setCursor(4, 71);
    printTrunc(appStr, 20);
    copyText(lastHomeApp, sizeof(lastHomeApp), appStr);
  }

  // Env line
  char envLine[40];
  if (isnan(sensors.temperature) || isnan(sensors.humidity)) {
    snprintf(envLine, sizeof(envLine), "ENV --");
  } else {
    snprintf(envLine, sizeof(envLine), "T %.1fC  H %.0f%%  P %.0fhPa",
             sensors.temperature, sensors.humidity, sensors.pressure);
  }
  if (strcmp(envLine, lastHomeEnv) != 0) {
    tft.fillRect(4, 84, 120, 10, theme.bg);
    tft.setTextColor(theme.text, theme.bg);
    tft.setCursor(4, 84);
    printTrunc(envLine, 20);
    copyText(lastHomeEnv, sizeof(lastHomeEnv), envLine);
  }

  // Music title
  char musicLine[64];
  if (state.musicPlaying && state.musicTitle[0] != '\0') {
    snprintf(musicLine, sizeof(musicLine), "> %s", state.musicTitle);
  } else if (state.musicTitle[0] != '\0') {
    snprintf(musicLine, sizeof(musicLine), "|| %s", state.musicTitle);
  } else {
    snprintf(musicLine, sizeof(musicLine), "No music");
  }
  if (strcmp(musicLine, lastHomeMusic) != 0) {
    tft.fillRect(4, 97, 120, 10, theme.bg);
    if (state.musicPlaying && state.musicTitle[0] != '\0') tft.setTextColor(theme.success, theme.bg);
    else if (state.musicTitle[0] != '\0') tft.setTextColor(theme.secondary, theme.bg);
    else tft.setTextColor(theme.secondary, theme.bg);
    tft.setCursor(4, 97);
    printTrunc(musicLine, 20);
    copyText(lastHomeMusic, sizeof(lastHomeMusic), musicLine);
  }

  // Battery
  int curBatt = batteryPercent();
  if (curBatt != lastHomeBatt) {
    drawBattery(4, 113);
    tft.fillRect(35, 114, 80, 10, theme.bg);
    tft.setTextColor(theme.text, theme.bg);
    tft.setCursor(35, 114);
    printTrunc(batteryLabel(), 12);
    lastHomeBatt = curBatt;
  }

  // Unread count
  if (state.unread > 0) {
    tft.setCursor(120, 114);
    tft.setTextColor(theme.warning, theme.bg);
    tft.print(state.unread);
  }
}

void drawMusicPage() {
  // Force full redraw if track changed
  if (strcmp(state.musicTitle, lastMusicTitle) != 0) {
    tftFullRedraw = true;
  }

  if (state.musicTitle[0] == '\0') {
    if (tftFullRedraw) {
      drawHeader("MUSIC");
      tft.setTextColor(theme.secondary, theme.bg);
      tft.setTextSize(2);
      tft.setCursor(4, 30);
      tft.print("Nothing");
      tft.setCursor(4, 52);
      tft.print("playing");
      tft.setTextSize(1);
      tft.setCursor(4, 88);
      tft.print("Open YouTube Music");
      tft.setCursor(4, 102);
      tft.print("on the PC to begin.");
      lastMusicTitle[0] = '\0';
      tftFullRedraw = false;
    }
    return;
  }

  if (tftFullRedraw) {
    drawHeader("MUSIC");

    // 40x40 Album Cover Art at (4, 20)
    if (hasCoverThumb && coverThumb != nullptr) {
      tft.drawRGBBitmap(4, 20, coverThumb, COVER_THUMB_W, COVER_THUMB_H);
      tft.drawRect(3, 19, 42, 42, theme.secondary);
    } else {
      tft.drawRect(3, 19, 42, 42, theme.secondary);
      tft.fillRect(4, 20, 40, 40, theme.headerBg);
      tft.setTextSize(2);
      tft.setTextColor(theme.accent, theme.headerBg);
      tft.setCursor(18, 32);
      tft.print("M");
      tft.setTextSize(1);
    }

    // Title & Artist aligned to the right of the cover (X=50)
    tft.setTextColor(theme.accent, theme.bg);
    tft.setTextSize(1);
    tft.setCursor(50, 22);
    printTrunc(state.musicTitle, 12);
    copyText(lastMusicTitle, sizeof(lastMusicTitle), state.musicTitle);

    tft.setTextColor(theme.secondary, theme.bg);
    tft.setCursor(50, 36);
    printTrunc(state.musicArtist[0] ? state.musicArtist : "Unknown artist", 12);

    tft.setTextColor(state.musicPlaying ? theme.success : theme.warning, theme.bg);
    tft.setCursor(50, 50);
    tft.print(state.musicPlaying ? "PLAYING" : "PAUSED");

    // Progress bar + text + status underneath (Y >= 68)
    int percentFull = 0;
    if (state.musicDuration > 0) {
      percentFull = (state.musicProgress * 100) / state.musicDuration;
    }
    drawBar(4, 68, 120, 8, (float)percentFull, theme.success);

    char progressTextFull[24];
    char currentTextFull[12];
    char totalTextFull[12];
    formatTime(state.musicProgress, currentTextFull, sizeof(currentTextFull));
    formatTime(state.musicDuration, totalTextFull, sizeof(totalTextFull));
    snprintf(progressTextFull, sizeof(progressTextFull), "%s / %s", currentTextFull, totalTextFull);
    tft.setTextColor(theme.text, theme.bg);
    tft.setCursor(4, 82);
    tft.print(progressTextFull);

    // Footer hints (static)
    tft.setTextColor(theme.secondary, theme.bg);
    tft.setCursor(4, 101);
    tft.print("SELECT play/pause");
    tft.setCursor(4, 114);
    tft.print("UP/DOWN pages");

    // Track for partial refresh
    lastMusicPlaying = state.musicPlaying;
    lastMusicPercent = percentFull;
    strncpy(lastProgressText, progressTextFull, sizeof(lastProgressText) - 1);
    lastProgressText[sizeof(lastProgressText) - 1] = '\0';

    tftFullRedraw = false;
  }

  // --- Dynamic: progress bar (smoothly animated) ---
  int percent = 0;
  if (state.musicDuration > 0) {
    percent = (state.musicProgress * 100) / state.musicDuration;
  }
  if (dispProgress < 0) dispProgress = percent;
  // Lerp toward target
  dispProgress += (percent - dispProgress) * 0.25f;
  if (fabs(dispProgress - percent) < 0.5f) dispProgress = percent;
  // Redraw if changed or full redraw
  if (fabs(dispProgress - lastDispProgress) > 0.4f || tftFullRedraw) {
    drawBar(4, 68, 120, 8, dispProgress, theme.success);
    lastDispProgress = dispProgress;
  }
  lastMusicPercent = percent;

  // --- Dynamic: progress text ---
  char progressText[24];
  char currentText[12];
  char totalText[12];
  formatTime(state.musicProgress, currentText, sizeof(currentText));
  formatTime(state.musicDuration, totalText, sizeof(totalText));
  snprintf(progressText, sizeof(progressText), "%s / %s", currentText, totalText);
  if (strcmp(progressText, lastProgressText) != 0) {
    tft.fillRect(4, 82, 120, 10, theme.bg);
    tft.setTextColor(theme.text, theme.bg);
    tft.setCursor(4, 82);
    tft.print(progressText);
    strncpy(lastProgressText, progressText, sizeof(lastProgressText) - 1);
    lastProgressText[sizeof(lastProgressText) - 1] = '\0';
  }

  // --- Dynamic: play/pause status (only if changed) ---
  if (state.musicPlaying != lastMusicPlaying) {
    tft.fillRect(50, 50, 74, 10, theme.bg);
    tft.setTextColor(state.musicPlaying ? theme.success : theme.warning, theme.bg);
    tft.setCursor(50, 50);
    tft.print(state.musicPlaying ? "PLAYING" : "PAUSED");
    lastMusicPlaying = state.musicPlaying;
  }
}

void restoreLyricsSlice(int x, int y, int w, int h) {
  if (hasLyricsBg && lyricsBg != nullptr) {
    for (int row = 0; row < h; row++) {
      int py = y + row;
      if (py >= 0 && py < TFT_H) {
        tft.drawRGBBitmap(x, py, &lyricsBg[py * TFT_W + x], w, 1);
      }
    }
  } else {
    tft.fillRect(x, y, w, h, theme.bg);
  }
}

int printWrappedLyric(const char* text, int x, int y, int maxChars, int maxLines) {
  if (text == nullptr || text[0] == '\0') {
    tft.setCursor(x, y);
    tft.print("...");
    return 1;
  }

  int length = strlen(text);
  int pos = 0;
  int line = 0;
  while (pos < length && line < maxLines) {
    int remaining = length - pos;
    int count = remaining < maxChars ? remaining : maxChars;
    if (pos + count < length) {
      int cut = count;
      while (cut > 0 && text[pos + cut] != ' ') cut--;
      if (cut >= maxChars / 2) count = cut;
    }

    char buffer[40];
    int copy = count;
    if (copy > (int)sizeof(buffer) - 1) copy = sizeof(buffer) - 1;
    strncpy(buffer, text + pos, copy);
    buffer[copy] = '\0';
    tft.setCursor(x, y + line * 12);
    tft.print(buffer);

    pos += count;
    while (pos < length && text[pos] == ' ') pos++;
    line++;
  }
  return line;
}

// Lyrics page partial-refresh tracking
static char lastLyricPrev[128] = "";
static char lastLyricCur[128] = "";
static char lastLyricNext[128] = "";
static int lastLyricIdx = -2;

void drawLyricsPage() {
  if (tftFullRedraw) {
    drawHeader("LYRICS");
    if (hasLyricsBg && lyricsBg != nullptr) {
      tft.drawRGBBitmap(0, 16, &lyricsBg[16 * TFT_W], TFT_W, 144);
    } else {
      tft.fillRect(0, 16, tft.width(), tft.height() - 16, theme.bg);
    }
    // Reset partial-refresh tracking on full redraw
    lastLyricPrev[0] = '\0';
    lastLyricCur[0] = '\0';
    lastLyricNext[0] = '\0';
    lastLyricIdx = -2;
    // Footer hint (static)
    tft.setTextColor(theme.secondary);
    tft.setCursor(4, 116);
    tft.print("UP/DOWN pages");
    tftFullRedraw = false;
  }

  if (!state.lyricsAvailable) {
    restoreLyricsSlice(0, 16, tft.width(), tft.height() - 16);
    tft.setTextSize(1);
    tft.setTextColor(theme.secondary);
    tft.setCursor(4, 30);
    if (state.musicTitle[0] == '\0') {
      tft.print("Nothing playing");
      tft.setCursor(4, 50);
      tft.print("Open YouTube Music");
      tft.setCursor(4, 62);
      tft.print("on the PC.");
    } else {
      tft.print("No lyrics found");
      tft.setTextColor(theme.accent);
      tft.setCursor(4, 50);
      printTrunc(state.musicTitle, 20);
      tft.setTextColor(theme.secondary);
      tft.setCursor(4, 64);
      printTrunc(state.musicArtist, 20);
    }
    tft.setCursor(4, 116);
    tft.print("UP/DOWN pages");
    return;
  }

  // Badge + index (only redraw if changed)
  bool badgeChanged = (lastLyricIdx != state.lyricIndex);
  if (badgeChanged || tftFullRedraw) {
    restoreLyricsSlice(0, 16, tft.width(), 16);
    tft.setTextSize(1);
    tft.setTextColor(state.lyricsSynced ? theme.success : theme.warning);
    tft.setCursor(4, 19);
    tft.print(state.lyricsSynced ? "SYNCED" : "UNSYNCED");

    if (state.lyricTotal > 0 && state.lyricIndex >= 0) {
      char pos[16];
      snprintf(pos, sizeof(pos), "%d/%d", state.lyricIndex + 1, state.lyricTotal);
      tft.setCursor(94, 19);
      tft.print(pos);
    }
    lastLyricIdx = state.lyricIndex;
  }

  // Previous line
  if (strcmp(state.lyricPrev, lastLyricPrev) != 0) {
    restoreLyricsSlice(4, 36, 120, 12);
    tft.setTextColor(theme.secondary);
    tft.setCursor(4, 36);
    printTrunc(state.lyricPrev, 20);
    copyText(lastLyricPrev, sizeof(lastLyricPrev), state.lyricPrev);
  }

  // Current line (wrapped, up to 4 lines)
  if (strcmp(state.lyricCur, lastLyricCur) != 0) {
    restoreLyricsSlice(4, 50, 120, 64);
    tft.setTextColor(theme.accent);
    int lines = printWrappedLyric(state.lyricCur, 4, 50, 20, 4);
    tft.setTextColor(theme.secondary);
    tft.setCursor(4, 50 + lines * 12 + 4);
    printTrunc(state.lyricNext, 20);
    copyText(lastLyricCur, sizeof(lastLyricCur), state.lyricCur);
    copyText(lastLyricNext, sizeof(lastLyricNext), state.lyricNext);
  } else if (strcmp(state.lyricNext, lastLyricNext) != 0) {
    // Only next changed
    restoreLyricsSlice(4, 50 + 4 * 12 + 4, 120, 12);
    tft.setTextColor(theme.secondary);
    tft.setCursor(4, 50 + 4 * 12 + 4);
    printTrunc(state.lyricNext, 20);
    copyText(lastLyricNext, sizeof(lastLyricNext), state.lyricNext);
  }
}

// PC page partial-refresh tracking
static float lastPcCpu = -999;
static float lastPcMem = -999;
static float lastPcGpu = -999;
static float lastPcCpuTemp = -999;
static float lastPcGpuTemp = -999;

void drawPcPage() {
  if (tftFullRedraw) {
    drawHeader("PC MONITOR");
    // Static labels
    tft.setTextColor(theme.text, theme.bg);
    tft.setTextSize(1);
    tft.setCursor(4, 24);
    tft.print("CPU");
    tft.setCursor(4, 50);
    tft.print("RAM");
    tft.setCursor(4, 76);
    tft.print("GPU");
    tft.setTextColor(theme.secondary, theme.bg);
    tft.setCursor(4, 114);
    tft.print("UP/DOWN pages");
    // Reset tracking
    lastPcCpu = -999;
    lastPcMem = -999;
    lastPcGpu = -999;
    lastPcCpuTemp = -999;
    lastPcGpuTemp = -999;
    tftFullRedraw = false;
  }

  uint16_t cpuColor = state.cpu > 80 ? ST77XX_RED : (state.cpu > 55 ? theme.warning : theme.success);
  uint16_t memColor = state.mem > 85 ? ST77XX_RED : (state.mem > 65 ? theme.warning : theme.success);
  uint16_t gpuColor = state.gpu > 80 ? ST77XX_RED : (state.gpu > 55 ? theme.warning : theme.success);

  // CPU bar + value
  if (state.cpu != lastPcCpu) {
    tft.fillRect(38, 22, 116, 9, theme.bg);
    drawBar(38, 22, 116, 9, state.cpu, cpuColor);
    tft.fillRect(4, 36, 60, 10, theme.bg);
    tft.setCursor(4, 36);
    tft.setTextColor(theme.text, theme.bg);
    if (state.cpu < 0) tft.print("--");
    else { tft.print(state.cpu, 0); tft.print("%"); }
    lastPcCpu = state.cpu;
  }

  // RAM bar + value
  if (state.mem != lastPcMem) {
    tft.fillRect(38, 48, 116, 9, theme.bg);
    drawBar(38, 48, 116, 9, state.mem, memColor);
    tft.fillRect(4, 62, 60, 10, theme.bg);
    tft.setCursor(4, 62);
    tft.setTextColor(theme.text, theme.bg);
    if (state.mem < 0) tft.print("--");
    else { tft.print(state.mem, 0); tft.print("%"); }
    lastPcMem = state.mem;
  }

  // GPU bar + value
  if (state.gpu != lastPcGpu) {
    tft.fillRect(38, 74, 116, 9, theme.bg);
    drawBar(38, 74, 116, 9, state.gpu, gpuColor);
    tft.fillRect(4, 88, 60, 10, theme.bg);
    tft.setCursor(4, 88);
    tft.setTextColor(theme.text, theme.bg);
    if (state.gpu < 0) tft.print("n/a");
    else { tft.print(state.gpu, 0); tft.print("%"); }
    lastPcGpu = state.gpu;
  }

  // CPU temp
  float curCpuTemp = state.cpuTemp >= 0 ? state.cpuTemp : state.thermalZone;
  if (curCpuTemp != lastPcCpuTemp) {
    tft.fillRect(4, 102, 80, 10, theme.bg);
    tft.setCursor(4, 102);
    tft.setTextColor(theme.text, theme.bg);
    if (state.cpuTemp >= 0) {
      tft.print("CPU ");
      tft.print(state.cpuTemp, 0);
      tft.print("C");
    } else if (state.thermalZone >= 0) {
      tft.print("TZ ");
      tft.print(state.thermalZone, 0);
      tft.print("C");
    } else {
      tft.print("CPU n/a");
    }
    lastPcCpuTemp = curCpuTemp;
  }

  // GPU temp
  if (state.gpuTemp != lastPcGpuTemp) {
    tft.fillRect(76, 102, 80, 10, theme.bg);
    tft.setCursor(76, 102);
    tft.setTextColor(theme.text, theme.bg);
    if (state.gpuTemp >= 0) {
      tft.print("GPU ");
      tft.print(state.gpuTemp, 0);
      tft.print("C");
    }
    lastPcGpuTemp = state.gpuTemp;
  }

  // VRAM / Fan line
  tft.fillRect(4, 114, 120, 12, theme.bg);
  tft.setTextColor(theme.secondary, theme.bg);
  tft.setCursor(4, 114);
  if (state.gpuVramMb > 0) {
    tft.print("VRAM ");
    tft.print(state.gpuVramMb / 1024.0f, 1);
    tft.print("GB");
    if (state.gpuFan >= 0) {
      tft.print(" FAN ");
      tft.print(state.gpuFan, 0);
      tft.print("%");
    }
  } else {
    tft.print("No GPU telemetry");
  }
}

// Env page partial-refresh tracking
static float lastEnvTemp = NAN;
static float lastEnvHum = NAN;
static float lastEnvPress = NAN;
static int lastEnvMic = -999;
static int lastEnvBattPct = -999;

void drawEnvPage() {
  if (tftFullRedraw) {
    drawHeader("ENVIRONMENT");
    // Static labels
    tft.setTextSize(1);
    tft.setTextColor(theme.text, theme.bg);
    tft.setCursor(4, 58);
    tft.print("Humidity ");
    tft.setCursor(4, 72);
    tft.print("Pressure ");
    tft.setTextColor(theme.secondary, theme.bg);
    tft.setCursor(4, 86);
    tft.print("MIC");
    tft.setCursor(4, 100);
    tft.print(sensors.bmeOk ? "BME ok" : "BME fallback");
    tft.setCursor(84, 100);
    tft.print(sensors.adxlOk ? "ADXL ok" : "ADXL off");
    tft.setCursor(4, 116);
    tft.print("UP/DOWN pages");
    // Reset tracking
    lastEnvTemp = NAN;
    lastEnvHum = NAN;
    lastEnvPress = NAN;
    lastEnvMic = -999;
    lastEnvBattPct = -999;
    tftFullRedraw = false;
  }

  // Temperature (big) - redraw if changed
  float curTemp = isnan(sensors.temperature) ? NAN : sensors.temperature;
  if (isnan(curTemp) != isnan(lastEnvTemp) || (!isnan(curTemp) && fabs(curTemp - lastEnvTemp) >= 0.1f)) {
    tft.fillRect(4, 23, 120, 24, theme.bg);
    tft.setTextColor(theme.accent, theme.bg);
    tft.setTextSize(3);
    tft.setCursor(4, 23);
    if (isnan(sensors.temperature)) tft.print("--.-C");
    else { tft.print(sensors.temperature, 1); tft.print("C"); }
    lastEnvTemp = curTemp;
  }

  // Humidity value - redraw if changed
  float curHum = isnan(sensors.humidity) ? NAN : sensors.humidity;
  if (isnan(curHum) != isnan(lastEnvHum) || (!isnan(curHum) && fabs(curHum - lastEnvHum) >= 0.1f)) {
    tft.fillRect(70, 58, 60, 10, theme.bg);
    tft.setTextSize(1);
    tft.setTextColor(theme.text, theme.bg);
    tft.setCursor(70, 58);
    if (isnan(sensors.humidity)) tft.print("--");
    else { tft.print(sensors.humidity, 1); tft.print("%"); }
    lastEnvHum = curHum;
  }

  // Pressure value - redraw if changed
  float curPress = isnan(sensors.pressure) ? NAN : sensors.pressure;
  if (isnan(curPress) != isnan(lastEnvPress) || (!isnan(curPress) && fabs(curPress - lastEnvPress) >= 1.0f)) {
    tft.fillRect(70, 72, 60, 10, theme.bg);
    tft.setTextSize(1);
    tft.setTextColor(theme.text, theme.bg);
    tft.setCursor(70, 72);
    if (isnan(sensors.pressure)) tft.print("--");
    else { tft.print(sensors.pressure, 0); tft.print(" hPa"); }
    lastEnvPress = curPress;
  }

  // Mic bar - redraw if changed
  int curMic = sensors.micOk ? sensors.micLevel : -999;
  if (curMic != lastEnvMic) {
    if (sensors.micOk) {
      tft.fillRect(30, 85, 126, 8, theme.bg);
      drawBar(30, 85, 126, 8, (float)sensors.micLevel, theme.accent);
    } else {
      tft.fillRect(30, 86, 60, 10, theme.bg);
      tft.setCursor(30, 86);
      tft.print("offline");
    }
    lastEnvMic = curMic;
  }

  // Battery - redraw if changed
  int curBatt = batteryPercent();
  if (curBatt != lastEnvBattPct) {
    drawBattery(4, 113);
    tft.fillRect(35, 114, 80, 10, theme.bg);
    tft.setTextColor(theme.text, theme.bg);
    tft.setCursor(35, 114);
    printTrunc(batteryLabel(), 12);
    lastEnvBattPct = curBatt;
  }
}

// Notifications page partial-refresh tracking
static int lastNoteCount = -1;

void drawNotificationsPage() {
  if (tftFullRedraw) {
    drawHeader("NOTIFICATIONS");
    lastNoteCount = -1;
    tftFullRedraw = false;
  }

  if (noteCount == 0) {
    if (lastNoteCount != 0) {
      tft.fillRect(0, 16, tft.width(), tft.height() - 16, theme.bg);
      tft.setTextColor(theme.secondary, theme.bg);
      tft.setTextSize(1);
      tft.setCursor(4, 30);
      tft.print("All clear.");
      tft.setCursor(4, 46);
      tft.print("Notifications appear here.");
      tft.setCursor(4, 70);
      tft.print("PC alerts, Pomodoro");
      tft.setCursor(4, 84);
      tft.print("timers and voice events.");
      lastNoteCount = 0;
    }
    return;
  }

  if (noteCount != lastNoteCount) {
    tft.fillRect(0, 16, tft.width(), tft.height() - 16, theme.bg);
    int shown = noteCount < 4 ? noteCount : 4;
    tft.setTextSize(1);
    for (int i = 0; i < shown; i++) {
      int y = 21 + (i * 25);
      tft.setTextColor(notes[i].read ? theme.secondary : theme.warning, theme.bg);
      tft.setCursor(4, y);
      tft.print(notes[i].read ? " " : "*");
      tft.print(" ");
      printTrunc(notes[i].title, 20);

      tft.setTextColor(notes[i].read ? theme.secondary : theme.text, theme.bg);
      tft.setCursor(13, y + 10);
      printTrunc(notes[i].message, 23);
    }

    if (noteCount > shown) {
      tft.setTextColor(theme.secondary, theme.bg);
      tft.setCursor(4, 114);
      tft.print("+");
      tft.print(noteCount - shown);
      tft.print(" more - SELECT to read");
    } else {
      tft.setTextColor(theme.secondary, theme.bg);
      tft.setCursor(4, 114);
      tft.print("SELECT marks next as read");
    }
    lastNoteCount = noteCount;
  }
}

// Pomodoro page partial-refresh tracking
static char lastPomoTimer[12] = "";
static bool lastPomoRunning = false;
static bool lastPomoIsBreak = false;
static int lastPomoSession = -1;

void drawPomodoroPage() {
  if (tftFullRedraw) {
    drawHeader("POMODORO");
    // Static labels
    tft.setTextSize(1);
    tft.setTextColor(theme.secondary, theme.bg);
    tft.setCursor(4, 86);
    tft.print("SELECT start/pause");
    tft.setCursor(4, 100);
    tft.print("UP/DOWN pages");
    tft.setCursor(4, 114);
    tft.print("25 / 5 / 15 min cycle");
    // Reset tracking
    lastPomoTimer[0] = '\0';
    lastPomoRunning = false;
    lastPomoIsBreak = false;
    lastPomoSession = -1;
    tftFullRedraw = false;
  }

  int minutes = pomodoro.remaining / 60;
  int seconds = pomodoro.remaining % 60;
  char timerText[12];
  snprintf(timerText, sizeof(timerText), "%02d:%02d", minutes, seconds);

  uint16_t timerColor = pomodoro.isBreak ? theme.success : theme.warning;
  if (!pomodoro.running) timerColor = theme.secondary;

  // Timer text (redraw if changed)
  if (strcmp(timerText, lastPomoTimer) != 0) {
    tft.fillRect(12, 27, 120, 32, theme.bg);
    tft.setTextColor(timerColor, theme.bg);
    tft.setTextSize(4);
    tft.setCursor(12, 27);
    tft.print(timerText);
    copyText(lastPomoTimer, sizeof(lastPomoTimer), timerText);
  }

  // Status line (redraw if state changed)
  if (pomodoro.running != lastPomoRunning || pomodoro.isBreak != lastPomoIsBreak || pomodoro.session != lastPomoSession) {
    tft.fillRect(4, 68, 120, 12, theme.bg);
    tft.setTextSize(1);
    tft.setTextColor(theme.text, theme.bg);
    tft.setCursor(4, 68);
    tft.print(pomodoro.isBreak ? "BREAK" : "FOCUS");
    tft.print("  session ");
    tft.print(pomodoro.session + 1);
    lastPomoRunning = pomodoro.running;
    lastPomoIsBreak = pomodoro.isBreak;
    lastPomoSession = pomodoro.session;
  }
}

void drawInspectionPage() {
  if (tftFullRedraw) {
    drawHeader("INSPECTION");
    tftFullRedraw = false;
  }

  if (inspectResultReady) {
    tft.fillRect(0, 16, tft.width(), tft.height() - 16, theme.bg);
    tft.setCursor(4, 24);
    tft.setTextColor(inspectResultClass[0] == 'N' ? theme.success : theme.warning, theme.bg);
    tft.setTextSize(2);
    tft.print(inspectResultClass);
    tft.setTextSize(1);
    tft.setTextColor(theme.text, theme.bg);
    tft.setCursor(4, 48);
    tft.print("Conf: ");
    tft.print(inspectResultConf * 100, 1);
    tft.print("%");
    tft.setCursor(4, 62);
    tft.print("Worst axis: ");
    tft.print(inspectResultAxis);
    tft.setTextColor(theme.secondary, theme.bg);
    tft.setCursor(4, 100);
    tft.print("SELECT: new capture");
    tft.setCursor(4, 114);
    tft.print("MODE: back to desk");
    return;
  }

  if (inspectCapturing) {
    tft.fillRect(0, 16, tft.width(), tft.height() - 16, theme.bg);
    tft.setTextColor(theme.warning, theme.bg);
    tft.setCursor(4, 30);
    tft.print("CAPTURING...");
    tft.setTextColor(theme.text, theme.bg);
    tft.setCursor(4, 50);
    tft.print(inspectCount);
    tft.print(" / ");
    tft.print(INSPECT_SAMPLES);
    tft.setCursor(4, 64);
    tft.print("samples");
    int pct = (inspectCount * 100) / INSPECT_SAMPLES;
    drawBar(4, 80, 120, 8, (float)pct, theme.warning);
    return;
  }

  // Idle - show live accel
  tft.fillRect(0, 16, tft.width(), tft.height() - 16, theme.bg);
  tft.setTextColor(theme.accent, theme.bg);
  tft.setCursor(4, 24);
  tft.print("INDUSTRIAL");
  tft.setTextSize(1);
  tft.setTextColor(theme.text, theme.bg);
  tft.setCursor(4, 50);
  tft.print("Inspection mode active");
  tft.setCursor(4, 64);
  tft.print("Sensor bridge ready");
  tft.setCursor(4, 78);
  tft.print(sensors.adxlOk ? "ADXL345 online" : "ADXL345 offline");
  tft.setCursor(4, 92);
  tft.print(sensors.bmeOk ? "BME280 online" : "BME280 offline");
  tft.setTextColor(theme.secondary, theme.bg);
  tft.setCursor(4, 106);
  tft.print("SELECT: capture");
  tft.setCursor(4, 118);
  tft.print("MODE: back to desk");
}

void updateBacklight(unsigned long now) {
  int target = 220;

  if (wakeActive(now)) {
    target = 255;
  } else if (state.backendOnline && strcmp(state.sleepStage, "deep_sleep") == 0) {
    target = 0;
  } else if (state.backendOnline && strcmp(state.sleepStage, "sleeping") == 0) {
    target = 18;
  } else if (state.backendOnline && strcmp(state.sleepStage, "sleepy") == 0) {
    target = 90;
  } else if (!state.backendOnline) {
    target = 150;
  }

  if (target != lastBacklight) {
    analogWrite(PIN_TFT_BL, target);
    lastBacklight = target;
  }
}

void drawTft(unsigned long now) {
  updateBacklight(now);

  if (mode == MODE_INSPECTION) {
    drawInspectionPage();
    return;
  }

  if (state.backendOnline && strcmp(state.sleepStage, "deep_sleep") == 0 && !wakeActive(now) && !tftFullRedraw) {
    return;
  }

  switch (page) {
    case PAGE_MUSIC: drawMusicPage(); break;
    case PAGE_LYRICS: drawLyricsPage(); break;
    case PAGE_PC: drawPcPage(); break;
    case PAGE_ENV: drawEnvPage(); break;
    case PAGE_NOTIFICATIONS: drawNotificationsPage(); break;
    case PAGE_POMODORO: drawPomodoroPage(); break;
    case PAGE_HOME:
    default: drawHome(); break;
  }
  tftFullRedraw = false;
}

// ----------------------------------------------------------------------------
// Arduino entry points
// ----------------------------------------------------------------------------
void setup() {
  Serial.setRxBufferSize(16384);
  Serial.begin(112000);
  delay(300);
  Serial.println();
  Serial.println("=== DeskBuddy boot ===");
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

  Serial.println("[boot] buttons"); Serial.flush();
  initButtons();
  Serial.println("[boot] oled"); Serial.flush();
  initOled();
  Serial.println("[boot] tft"); Serial.flush();
  initTft();
  Serial.println("[boot] sensors"); Serial.flush();
  initSensors();
  Serial.println("[boot] mic"); Serial.flush();
  initMic();
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
  serializeJson(txDoc, Serial);
  Serial.println();
  Serial.println("[boot] setup complete");
  Serial.flush();
}

void loop() {
  unsigned long now = millis();

  readSerial();

  if (now - lastMotionReadMs >= MOTION_MS) {
    readMotion();
    lastMotionReadMs = now;
  }

  if (now - lastEnvReadMs >= ENV_MS) {
    readEnvironment();
    lastEnvReadMs = now;
  }

  if (now - lastBatteryReadMs >= BATTERY_MS) {
    updateBattery();
    lastBatteryReadMs = now;
  }

  if (now - lastMicReadMs >= MIC_MS) {
    readMicrophone();
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
    drawEyes(now);
    lastEyeMs = now;
  }

  if (tftDirty || now - lastTftMs >= TFT_REFRESH_MS) {
    drawTft(now);
    tftDirty = false;
    lastTftMs = now;
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
}

