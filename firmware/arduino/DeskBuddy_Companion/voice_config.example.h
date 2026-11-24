#pragma once
// Copy this file to voice_config.h and fill in your values.
// voice_config.h is gitignored so credentials are never committed.
//
// Alternatively, send the values at runtime over serial (stored in NVS):
//   {"cmd":"wifi","payload":{"ssid":"...","pass":"..."}}
//   {"cmd":"voice_server","payload":{"url":"http://192.168.1.50:8080"}}
//
// The backend URL must be the PC's LAN address, not 127.0.0.1, because the
// request comes from the ESP32. Start uvicorn with --host 0.0.0.0.

#define VOICE_WIFI_SSID "YOUR_WIFI_SSID"
#define VOICE_WIFI_PASS "YOUR_WIFI_PASSWORD"
#define VOICE_SERVER_URL "http://192.168.1.50:8080"

// Optional: keep Wi-Fi associated all the time. The default (0) connects on
// demand and disconnects after two minutes idle, which saves battery power.
// #define VOICE_WIFI_ALWAYS_ON 1
