// Test C: Standard Adafruit GFX font
#include <Arduino.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>

#define TFT_CS 10
#define TFT_DC 13
#define TFT_RST 14
#define TFT_MOSI 11
#define TFT_SCLK 12
#define TFT_BL 15
#define W 128
#define H 160

Adafruit_ST7735 tft(TFT_CS, TFT_DC, TFT_RST);
GFXcanvas16 sprite(W, H);

const char* lines[] = {
  "MUSIC",
  "Sweet",
  "Justin Bieber",
  "We keep moving forward",
  "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
  "0123456789"
};

void testDirect() {
  tft.fillScreen(ST77XX_BLACK);
  tft.setTextColor(ST77XX_WHITE);
  tft.setTextSize(1);
  int y = 10;
  for (int i = 0; i < 6; i++) {
    tft.setCursor(4, y);
    tft.print(lines[i]);
    y += 12;
  }
  delay(3000);
}

void testSprite() {
  sprite.fillScreen(ST77XX_BLACK);
  sprite.setTextColor(ST77XX_WHITE);
  sprite.setTextSize(1);
  int y = 10;
  for (int i = 0; i < 6; i++) {
    sprite.setCursor(4, y);
    sprite.print(lines[i]);
    y += 12;
  }
  tft.drawRGBBitmap(0, 0, sprite.getBuffer(), W, H);
  delay(3000);
}

void setup() {
  pinMode(TFT_BL, OUTPUT);
  analogWrite(TFT_BL, 220);
  SPI.begin(TFT_SCLK, -1, TFT_MOSI, TFT_CS);
  tft.initR(INITR_GREENTAB);
  tft.setRotation(2);
  tft.fillScreen(ST77XX_BLACK);

  testDirect();  // Test C part 1: direct to TFT
  testSprite();  // Test C part 2: through sprite
}

void loop() {}