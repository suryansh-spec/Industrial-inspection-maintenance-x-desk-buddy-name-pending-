// Optional addressable LED strip support (WLED-inspired effects & audio-reactive modes).
// Requires Adafruit NeoPixel library. Enabled only when ENABLE_LED_STRIP is
// defined (auto-defined in the main sketch when the library is present).

#include "led_strip.h"

#if LED_STRIP_AVAILABLE

#include <math.h>

#define PIN_LED_DATA      21
#define LED_DEFAULT_COUNT 16
#define LED_MAX_COUNT     120
#define LED_FRAME_MS      25   // ~40 fps for smooth WLED animations

static Adafruit_NeoPixel strip(LED_DEFAULT_COUNT, PIN_LED_DATA, NEO_GRB + NEO_KHZ800);

static bool ledOk = false;
static bool ledPower = true;
static bool ledDirty = true;
static uint8_t ledBrightness = 140;
static uint8_t ledSpeed = 128;      // 0..255
static uint8_t ledIntensity = 128;  // 0..255
static int ledCount = LED_DEFAULT_COUNT;
static char ledEffect[24] = "auto";
static char ledMode[16] = "auto";   // auto | music | ambient
static uint8_t ledR = 120, ledG = 40, ledB = 200;
static uint8_t ledR2 = 0, ledG2 = 200, ledB2 = 220;

static unsigned long lastFrameMs = 0;
static uint32_t animPhase = 0;
static int cometPos = 0;
static int chasePos = 0;
static int scanPos = 0;
static int scanDir = 1;
static unsigned long lastBeatMs = 0;
static uint8_t pcLvl = 0, pcBass = 0, pcMid = 0, pcHigh = 0;
static unsigned long pcLastAudioMs = 0;
static unsigned long pcLastNonZeroMs = 0;
static uint8_t twinkleMask[LED_MAX_COUNT];
static uint8_t fireHeat[LED_MAX_COUNT];
static int ripplePos = -1;
static uint16_t rippleHue = 0;

static void ledShowColor(uint32_t c) {
  for (int i = 0; i < ledCount; i++) strip.setPixelColor(i, c);
}

static uint32_t ledColor(uint8_t r, uint8_t g, uint8_t b) {
  return strip.Color(r, g, b);
}

static uint32_t ledBlend(uint8_t r1, uint8_t g1, uint8_t b1,
                         uint8_t r2, uint8_t g2, uint8_t b2, uint8_t t) {
  uint8_t r = (uint8_t)(((uint16_t)r1 * (255 - t) + (uint16_t)r2 * t) / 255);
  uint8_t g = (uint8_t)(((uint16_t)g1 * (255 - t) + (uint16_t)g2 * t) / 255);
  uint8_t b = (uint8_t)(((uint16_t)b1 * (255 - t) + (uint16_t)b2 * t) / 255);
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
  for (int i = 0; i < LED_MAX_COUNT; i++) {
    twinkleMask[i] = 0;
    fireHeat[i] = 0;
  }
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

  if (payload.containsKey("speed")) {
    ledSpeed = (uint8_t)constrain(payload["speed"].as<int>(), 0, 255);
    ledDirty = true;
  }

  if (payload.containsKey("intensity")) {
    ledIntensity = (uint8_t)constrain(payload["intensity"].as<int>(), 0, 255);
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

void ledApplyAudio(JsonObjectConst payload) {
  if (!ledOk) return;
  pcLvl  = (uint8_t)constrain(payload["lvl"]  | 0, 0, 100);
  pcBass = (uint8_t)constrain(payload["b"]    | 0, 0, 100);
  pcMid  = (uint8_t)constrain(payload["m"]    | 0, 0, 100);
  pcHigh = (uint8_t)constrain(payload["h"]    | 0, 0, 100);
  int beat = payload["beat"] | 0;
  unsigned long now = millis();
  pcLastAudioMs = now;
  if (pcLvl > 2) pcLastNonZeroMs = now;
  if (beat) lastBeatMs = now;
}

void ledUpdate(unsigned long now) {
  if (!ledOk) return;
  if (!ledPower) return;
  if (now - lastFrameMs < LED_FRAME_MS) return;
  lastFrameMs = now;

  // Decay backend audio if stream pauses or disconnects
  if (now - pcLastAudioMs > 600) {
    pcLvl  = (pcLvl  > 5) ? (pcLvl  - 5) : 0;
    pcBass = (pcBass > 5) ? (pcBass - 5) : 0;
    pcMid  = (pcMid  > 5) ? (pcMid  - 5) : 0;
    pcHigh = (pcHigh > 5) ? (pcHigh - 5) : 0;
  }

  bool audioLive = (pcLvl > 2) || (now - pcLastNonZeroMs < 1500);

  // Decide effective mode
  bool musicMode = false;
  if (strcmp(ledMode, "music") == 0) musicMode = true;
  else if (strcmp(ledMode, "auto") == 0) musicMode = audioLive;

  const char* eff = ledEffect;
  char autoEff[24];
  if (strcmp(eff, "auto") == 0) {
    if (musicMode) strcpy(autoEff, "freq_pulse");
    else strcpy(autoEff, "rainbow_cycle");
    eff = autoEff;
  }

  uint32_t stepInc = 1 + (ledSpeed >> 5);  // 1..8 per frame
  animPhase += stepInc;

  int energy = pcLvl;

  if (strcmp(eff, "solid") == 0) {
    ledShowColor(ledColor(ledR, ledG, ledB));

  } else if (strcmp(eff, "blink") == 0) {
    uint32_t period = max<uint32_t>(4, 40 - (ledSpeed >> 3));
    bool on = ((animPhase / period) % 2) == 0;
    ledShowColor(on ? ledColor(ledR, ledG, ledB) : ledColor(0, 0, 0));

  } else if (strcmp(eff, "breathing") == 0) {
    float s = (sinf(animPhase * 0.045f) + 1.0f) * 0.5f;
    s = 0.08f + 0.92f * (s * s);
    ledShowColor(ledColor((uint8_t)(ledR * s), (uint8_t)(ledG * s), (uint8_t)(ledB * s)));

  } else if (strcmp(eff, "rainbow") == 0) {
    uint16_t baseHue = (uint16_t)(animPhase * 180);
    for (int i = 0; i < ledCount; i++) {
      uint16_t h = baseHue + (uint16_t)(i * 65535 / (ledCount > 1 ? ledCount : 2));
      strip.setPixelColor(i, strip.ColorHSV(h, 255, 255));
    }

  } else if (strcmp(eff, "rainbow_cycle") == 0) {
    uint16_t h = (uint16_t)(animPhase * 140);
    for (int i = 0; i < ledCount; i++) {
      strip.setPixelColor(i, strip.ColorHSV(h + (uint16_t)(i * (ledIntensity * 12)), 255, 255));
    }

  } else if (strcmp(eff, "pride") == 0) {
    for (int i = 0; i < ledCount; i++) {
      float p1 = sinf((float)i * 0.45f + animPhase * 0.04f);
      float p2 = sinf((float)i * 0.25f - animPhase * 0.025f);
      uint16_t h = (uint16_t)(((p1 + p2 + 2.0f) * 0.25f) * 65535.0f + animPhase * 60);
      uint8_t v = (uint8_t)(160 + 95 * (0.5f + 0.5f * sinf((float)i * 0.6f + animPhase * 0.05f)));
      strip.setPixelColor(i, strip.ColorHSV(h, 240, v));
    }

  } else if (strcmp(eff, "aurora") == 0) {
    for (int i = 0; i < ledCount; i++) {
      float w1 = 0.5f + 0.5f * sinf((float)i * 0.5f + animPhase * 0.03f);
      float w2 = 0.5f + 0.5f * cosf((float)i * 0.35f - animPhase * 0.022f);
      uint8_t t = (uint8_t)(w1 * 255.0f);
      uint8_t bright = (uint8_t)(80 + 175 * w2);
      uint8_t r = (uint8_t)(((uint16_t)ledR * (255 - t) + (uint16_t)ledR2 * t) * bright / 65025);
      uint8_t g = (uint8_t)(((uint16_t)ledG * (255 - t) + (uint16_t)ledG2 * t) * bright / 65025);
      uint8_t b = (uint8_t)(((uint16_t)ledB * (255 - t) + (uint16_t)ledB2 * t) * bright / 65025);
      strip.setPixelColor(i, strip.Color(r, g, b));
    }

  } else if (strcmp(eff, "comet") == 0) {
    for (int i = 0; i < ledCount; i++) {
      uint32_t c = strip.getPixelColor(i);
      uint8_t r = (uint8_t)(((c >> 16) & 0xFF) * 180 / 255);
      uint8_t g = (uint8_t)(((c >> 8) & 0xFF) * 180 / 255);
      uint8_t b = (uint8_t)((c & 0xFF) * 180 / 255);
      strip.setPixelColor(i, strip.Color(r, g, b));
    }
    if ((animPhase % 2) == 0 || ledSpeed > 180) {
      cometPos = (cometPos + 1) % ledCount;
    }
    strip.setPixelColor(cometPos, ledColor(ledR, ledG, ledB));

  } else if (strcmp(eff, "scanner") == 0) {
    for (int i = 0; i < ledCount; i++) {
      uint32_t c = strip.getPixelColor(i);
      uint8_t r = (uint8_t)(((c >> 16) & 0xFF) * 165 / 255);
      uint8_t g = (uint8_t)(((c >> 8) & 0xFF) * 165 / 255);
      uint8_t b = (uint8_t)((c & 0xFF) * 165 / 255);
      strip.setPixelColor(i, strip.Color(r, g, b));
    }
    if ((animPhase % 2) == 0 || ledSpeed > 180) {
      scanPos += scanDir;
      if (scanPos >= ledCount - 1) { scanPos = ledCount - 1; scanDir = -1; }
      if (scanPos <= 0) { scanPos = 0; scanDir = 1; }
    }
    strip.setPixelColor(scanPos, ledColor(ledR, ledG, ledB));

  } else if (strcmp(eff, "chase") == 0) {
    strip.clear();
    if ((animPhase % 2) == 0 || ledSpeed > 180) {
      chasePos = (chasePos + 1) % 3;
    }
    for (int i = chasePos; i < ledCount; i += 3) {
      strip.setPixelColor(i, ledColor(ledR, ledG, ledB));
    }

  } else if (strcmp(eff, "fire") == 0) {
    uint8_t cooling = (uint8_t)(20 + (255 - ledIntensity) / 6);
    for (int i = 0; i < ledCount; i++) {
      int cool = random(0, cooling);
      fireHeat[i] = (fireHeat[i] > cool) ? (fireHeat[i] - cool) : 0;
      if (random(0, 255) < (40 + ledIntensity / 2)) {
        fireHeat[i] = (uint8_t)min<int>(255, (int)fireHeat[i] + (int)random(90, 180));
      }
      uint8_t h = fireHeat[i];
      uint8_t r = min(255, (int)h * 2);
      uint8_t g = (h > 85) ? (uint8_t)((h - 85) * 3 / 2) : 0;
      uint8_t b = (h > 200) ? (uint8_t)((h - 200) * 2) : 0;
      strip.setPixelColor(i, strip.Color(r, g, b));
    }

  } else if (strcmp(eff, "twinkle") == 0 || strcmp(eff, "sparkle") == 0) {
    bool isSparkle = (strcmp(eff, "sparkle") == 0);
    for (int i = 0; i < ledCount; i++) {
      if (random(0, 255) < (12 + (ledIntensity >> 3))) twinkleMask[i] = 255;
      else if (twinkleMask[i] > 18) twinkleMask[i] -= 18;
      else twinkleMask[i] = 0;
      uint8_t v = twinkleMask[i];
      if (isSparkle) {
        strip.setPixelColor(i, ledBlend(ledR / 6, ledG / 6, ledB / 6, 255, 255, 255, v));
      } else {
        strip.setPixelColor(i, strip.Color(
          (uint8_t)(ledR * v / 255),
          (uint8_t)(ledG * v / 255),
          (uint8_t)(ledB * v / 255)));
      }
    }

  } else if (strcmp(eff, "ripple") == 0) {
    for (int i = 0; i < ledCount; i++) {
      uint32_t c = strip.getPixelColor(i);
      uint8_t r = (uint8_t)(((c >> 16) & 0xFF) * 185 / 255);
      uint8_t g = (uint8_t)(((c >> 8) & 0xFF) * 185 / 255);
      uint8_t b = (uint8_t)((c & 0xFF) * 185 / 255);
      strip.setPixelColor(i, strip.Color(r, g, b));
    }
    if (ripplePos < 0 || ripplePos > ledCount / 2) {
      ripplePos = 0;
      rippleHue = (uint16_t)(animPhase * 410);
    } else if ((animPhase % 2) == 0) {
      int c1 = (ledCount / 2 + ripplePos) % ledCount;
      int c2 = (ledCount / 2 - ripplePos + ledCount) % ledCount;
      uint32_t rc = strip.ColorHSV(rippleHue, 255, 255);
      strip.setPixelColor(c1, rc);
      strip.setPixelColor(c2, rc);
      ripplePos++;
    }

  } else if (strcmp(eff, "gradient") == 0 || strcmp(eff, "palette_wave") == 0) {
    for (int i = 0; i < ledCount; i++) {
      float wave = 0.5f + 0.5f * sinf((float)i * (6.283f / ledCount) + animPhase * 0.05f);
      strip.setPixelColor(i, ledBlend(ledR, ledG, ledB, ledR2, ledG2, ledB2, (uint8_t)(wave * 255.0f)));
    }

  } else if (strcmp(eff, "vu") == 0) {
    int lit = (energy * ledCount) / 100;
    if (lit > ledCount) lit = ledCount;
    strip.clear();
    for (int i = 0; i < lit; i++) {
      uint8_t t = (uint8_t)((i * 255) / (ledCount > 1 ? ledCount - 1 : 1));
      strip.setPixelColor(i, ledBlend(ledR, ledG, ledB, ledR2, ledG2, ledB2, t));
    }
    if (now - lastBeatMs < 65 && energy > 25) {
      ledShowColor(ledColor(255, 255, 255));
    }

  } else if (strcmp(eff, "freq_pulse") == 0) {
    // 3-band PC audio spectrum across the ring: Bass -> Mid -> High
    if (energy == 0) {
      strip.clear();
    } else {
      float gain = 0.65f + (ledIntensity / 180.0f);
      int third = max(1, ledCount / 3);
      for (int i = 0; i < ledCount; i++) {
        uint8_t bandVal = (i < third) ? pcBass : (i < third * 2 ? pcMid : pcHigh);
        float v = constrain((bandVal / 100.0f) * gain, 0.0f, 1.0f);
        uint16_t h = (uint16_t)(animPhase * 45 + (i * 65535 / ledCount));
        if (now - lastBeatMs < 70 && i < third) {
          strip.setPixelColor(i, ledColor(255, 255, 255));
        } else {
          strip.setPixelColor(i, strip.ColorHSV(h, 240, (uint8_t)(v * 255.0f)));
        }
      }
    }

  } else if (strcmp(eff, "juggle_beat") == 0) {
    if (energy == 0) {
      strip.clear();
    } else {
      for (int i = 0; i < ledCount; i++) {
        uint32_t c = strip.getPixelColor(i);
        uint8_t r = (uint8_t)(((c >> 16) & 0xFF) * 160 / 255);
        uint8_t g = (uint8_t)(((c >> 8) & 0xFF) * 160 / 255);
        uint8_t b = (uint8_t)((c & 0xFF) * 160 / 255);
        strip.setPixelColor(i, strip.Color(r, g, b));
      }
      float rate = 0.04f + 0.10f * (energy / 100.0f);
      uint8_t v = (uint8_t)constrain(60 + (energy * 2), 60, 255);
      for (int d = 0; d < 4; d++) {
        int pos = (int)((0.5f + 0.5f * sinf((float)millis() * 0.002f * (1.0f + d * 0.35f) + rate)) * (ledCount - 1));
        strip.setPixelColor(pos, strip.ColorHSV((uint16_t)(d * 16384 + animPhase * 90), 255, v));
      }
    }

  } else if (strcmp(eff, "beat") == 0) {
    if (energy == 0) {
      strip.clear();
    } else {
      float s = (now - lastBeatMs < 100) ? 1.0f : (0.10f + 0.80f * (pcBass / 100.0f));
      s = constrain(s, 0.05f, 1.0f);
      ledShowColor(ledColor((uint8_t)(ledR * s), (uint8_t)(ledG * s), (uint8_t)(ledB * s)));
    }

  } else {
    ledShowColor(ledColor(ledR, ledG, ledB));
  }

  strip.show();
}

#endif // LED_STRIP_AVAILABLE
