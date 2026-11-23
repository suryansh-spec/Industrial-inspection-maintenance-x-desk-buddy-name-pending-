// Optional addressable LED strip support.
// Requires Adafruit NeoPixel library. Enabled only when ENABLE_LED_STRIP is
// defined (auto-defined in the main sketch when the library is present).

#include "led_strip.h"

#if LED_STRIP_AVAILABLE

#include <math.h>

#define PIN_LED_DATA    2
#define LED_DEFAULT_COUNT 24
#define LED_MAX_COUNT   120
#define LED_FRAME_MS    33

static Adafruit_NeoPixel strip(LED_DEFAULT_COUNT, PIN_LED_DATA, NEO_GRB + NEO_KHZ800);

static bool ledOk = false;
static bool ledPower = true;
static bool ledDirty = true;
static uint8_t ledBrightness = 128;
static int ledCount = LED_DEFAULT_COUNT;
static char ledEffect[24] = "auto";
static char ledMode[16] = "auto";   // auto | music | ambient
static uint8_t ledR = 120, ledG = 40, ledB = 200;
static uint8_t ledR2 = 0, ledG2 = 200, ledB2 = 220;

static unsigned long lastFrameMs = 0;
static uint16_t animPhase = 0;
static int cometPos = 0;
static int chasePos = 0;
static unsigned long lastBeatMs = 0;
static int lastMicLevel = 0;
static uint8_t twinkleMask[LED_MAX_COUNT];

static void ledShowColor(uint32_t c) {
  for (int i = 0; i < ledCount; i++) strip.setPixelColor(i, c);
}

static uint32_t ledColor(uint8_t r, uint8_t g, uint8_t b) {
  return strip.Color(r, g, b);
}

static void parseHexColor(const char* hex, uint8_t* r, uint8_t* g, uint8_t* b) {
  if (hex == nullptr || hex[0] != '#') return;
  int len = 0;
  while (hex[1 + len] != '\0' && len < 8) len++;
  unsigned long val = 0;
  for (int i = 0; i < len; i++) {
    char c = hex[1 + i];
    int d;
    if (c >= '0' && c <= '9') d = c - '0';
    else if (c >= 'a' && c <= 'f') d = c - 'a' + 10;
    else if (c >= 'A' && c <= 'F') d = c - 'A' + 10;
    else return;
    val = (val << 4) | (unsigned long)d;
  }
  if (len == 3) {
    *r = (uint8_t)(((val >> 8) & 0xF) * 17);
    *g = (uint8_t)(((val >> 4) & 0xF) * 17);
    *b = (uint8_t)((val & 0xF) * 17);
  } else if (len == 6) {
    *r = (uint8_t)((val >> 16) & 0xFF);
    *g = (uint8_t)((val >> 8) & 0xFF);
    *b = (uint8_t)(val & 0xFF);
  }
}

void ledInit() {
  ledCount = constrain(LED_DEFAULT_COUNT, 1, LED_MAX_COUNT);
  strip.updateLength(ledCount);
  strip.setBrightness(ledBrightness);
  strip.begin();
  strip.clear();
  strip.show();
  for (int i = 0; i < LED_MAX_COUNT; i++) twinkleMask[i] = 0;
  ledOk = true;
  lastFrameMs = millis();
  Serial.printf("[led] init ok count=%d pin=%d\n", ledCount, PIN_LED_DATA);
}

bool ledIsOk() { return ledOk; }

void ledApplyCommand(JsonObjectConst payload) {
  if (!ledOk) return;

  if (payload.containsKey("power")) {
    ledPower = payload["power"].as<bool>();
    if (!ledPower) {
      strip.clear();
      strip.show();
    }
    ledDirty = true;
  }

  if (payload.containsKey("brightness")) {
    int b = payload["brightness"].as<int>();
    ledBrightness = (uint8_t)constrain(b, 0, 255);
    strip.setBrightness(ledBrightness);
    ledDirty = true;
  }

  if (payload.containsKey("count")) {
    int c = payload["count"].as<int>();
    if (c > 0 && c <= LED_MAX_COUNT) {
      ledCount = c;
      strip.updateLength(ledCount);
      ledDirty = true;
    }
  }

  const char* effect = payload["effect"] | "";
  if (effect[0] != '\0') {
    copyText(ledEffect, sizeof(ledEffect), effect);
    ledDirty = true;
  }

  const char* mode = payload["mode"] | "";
  if (mode[0] != '\0') {
    copyText(ledMode, sizeof(ledMode), mode);
    ledDirty = true;
  }

  const char* color = payload["color"] | "";
  if (color[0] != '\0') {
    parseHexColor(color, &ledR, &ledG, &ledB);
    ledDirty = true;
  }

  const char* color2 = payload["color2"] | "";
  if (color2[0] != '\0') {
    parseHexColor(color2, &ledR2, &ledG2, &ledB2);
    ledDirty = true;
  }
}

void ledUpdate(unsigned long now) {
  if (!ledOk) return;
  if (!ledPower) return;
  if (now - lastFrameMs < LED_FRAME_MS) return;
  lastFrameMs = now;

  // Decide effective mode
  bool musicMode = false;
  if (strcmp(ledMode, "music") == 0) musicMode = true;
  else if (strcmp(ledMode, "auto") == 0) musicMode = state.musicPlaying;

  const char* eff = ledEffect;
  char autoEff[16];
  if (strcmp(eff, "auto") == 0) {
    if (musicMode) strcpy(autoEff, "vu");
    else strcpy(autoEff, "rainbow");
    eff = autoEff;
  }

  animPhase++;

  // VU / beat pulse use mic level
  int mic = sensors.micLevel;
  if (mic < 0) mic = 0;
  int delta = mic - lastMicLevel;
  if (delta < 0) delta = -delta;
  if (delta > 12 && now - lastBeatMs > 120) {
    lastBeatMs = now;
  }
  lastMicLevel = mic;

  if (strcmp(eff, "solid") == 0) {
    ledShowColor(ledColor(ledR, ledG, ledB));
  } else if (strcmp(eff, "breathing") == 0) {
    float s = (sinf(animPhase * 0.05f) + 1.0f) * 0.5f;
    uint8_t r = (uint8_t)(ledR * s);
    uint8_t g = (uint8_t)(ledG * s);
    uint8_t b = (uint8_t)(ledB * s);
    ledShowColor(ledColor(r, g, b));
  } else if (strcmp(eff, "rainbow") == 0) {
    for (int i = 0; i < ledCount; i++) {
      uint16_t h = (i * 65535 / (ledCount > 1 ? ledCount : 2)) + animPhase * 256;
      strip.setPixelColor(i, strip.ColorHSV(h, 255, 255));
    }
  } else if (strcmp(eff, "comet") == 0) {
    strip.clear();
    cometPos = (cometPos + 1) % ledCount;
    for (int t = 0; t < 5; t++) {
      int idx = (cometPos - t + ledCount) % ledCount;
      uint8_t fade = (uint8_t)(255 - t * 50);
      strip.setPixelColor(idx, strip.Color(
        (uint8_t)(ledR * fade / 255),
        (uint8_t)(ledG * fade / 255),
        (uint8_t)(ledB * fade / 255)));
    }
  } else if (strcmp(eff, "chase") == 0) {
    strip.clear();
    chasePos = (chasePos + 1) % (ledCount + 4);
    for (int s = 0; s < 3; s++) {
      int idx = chasePos - s * 4;
      if (idx >= 0 && idx < ledCount) {
        strip.setPixelColor(idx, ledColor(ledR, ledG, ledB));
      }
    }
  } else if (strcmp(eff, "fire") == 0) {
    for (int i = 0; i < ledCount; i++) {
      uint8_t flick = (uint8_t)random(180, 255);
      strip.setPixelColor(i, strip.Color(flick, (uint8_t)(flick * 0.4f), 0));
    }
  } else if (strcmp(eff, "twinkle") == 0) {
    for (int i = 0; i < ledCount; i++) {
      if (random(0, 30) == 0) twinkleMask[i] = 255;
      else if (twinkleMask[i] > 20) twinkleMask[i] -= 20;
      else twinkleMask[i] = 0;
      uint8_t v = twinkleMask[i];
      strip.setPixelColor(i, strip.Color(
        (uint8_t)(ledR * v / 255),
        (uint8_t)(ledG * v / 255),
        (uint8_t)(ledB * v / 255)));
    }
  } else if (strcmp(eff, "gradient") == 0) {
    for (int i = 0; i < ledCount; i++) {
      float t = (float)i / (ledCount > 1 ? ledCount - 1 : 1);
      uint8_t r = (uint8_t)(ledR * (1 - t) + ledR2 * t);
      uint8_t g = (uint8_t)(ledG * (1 - t) + ledG2 * t);
      uint8_t b = (uint8_t)(ledB * (1 - t) + ledB2 * t);
      strip.setPixelColor(i, ledColor(r, g, b));
    }
  } else if (strcmp(eff, "vu") == 0) {
    int lit = (mic * ledCount) / 100;
    if (lit < 0) lit = 0;
    if (lit > ledCount) lit = ledCount;
    uint32_t c = ledColor(ledR, ledG, ledB);
    strip.clear();
    for (int i = 0; i < lit; i++) strip.setPixelColor(i, c);
    // beat flash
    if (now - lastBeatMs < 80) {
      ledShowColor(ledColor(255, 255, 255));
    }
  } else if (strcmp(eff, "beat") == 0) {
    float s = (now - lastBeatMs < 100) ? 1.0f : 0.15f;
    uint8_t r = (uint8_t)(ledR * s);
    uint8_t g = (uint8_t)(ledG * s);
    uint8_t b = (uint8_t)(ledB * s);
    ledShowColor(ledColor(r, g, b));
  } else {
    ledShowColor(ledColor(ledR, ledG, ledB));
  }

  strip.show();
}

#endif // LED_STRIP_AVAILABLE
