#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>

// Optional addressable LED strip support (WS2812B/NeoPixel).
// Auto-enables when Adafruit NeoPixel library is installed and ENABLE_LED_STRIP
// is defined. All functions are no-ops when unavailable, so callers never need
// their own #if guards beyond including this header.

#if defined(ENABLE_LED_STRIP)
#include <Adafruit_NeoPixel.h>
#define LED_STRIP_AVAILABLE 1
#else
#define LED_STRIP_AVAILABLE 0
#endif

#if LED_STRIP_AVAILABLE
void ledInit();
void ledUpdate(unsigned long now);
void ledApplyCommand(JsonObjectConst payload);
void ledApplyAudio(JsonObjectConst payload);
bool ledIsOk();
#else
inline void ledInit() {}
inline void ledUpdate(unsigned long) {}
inline void ledApplyCommand(JsonObjectConst) {}
inline void ledApplyAudio(JsonObjectConst) {}
inline bool ledIsOk() { return false; }
#endif
