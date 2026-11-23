// Isolated font/rendering diagnostic sketch (Test B: sprite -> TFT)
#include <Arduino.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <U8g2_for_Adafruit_GFX.h>

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
U8G2_FOR_ADAFRUIT_GFX u8g2gfx;

void setup() {
  pinMode(TFT_BL, OUTPUT);
  analogWrite(TFT_BL, 220);
  SPI.begin(TFT_SCLK, -1, TFT_MOSI, TFT_CS);
  tft.initR(INITR_GREENTAB);
  tft.setRotation(2);
  tft.fillScreen(ST77XX_BLACK);

  sprite.fillScreen(ST77XX_BLACK);
  u8g2gfx.begin(sprite);
  u8g2gfx.setFontMode(1);
  u8g2gfx.setForegroundColor(ST77XX_WHITE);
  u8g2gfx.setBackgroundColor(ST77XX_BLACK);

  const uint8_t* fonts[] = {
    u8g2_font_6x12_tf,
    u8g2_font_7x14_tf,
    u8g2_font_helvR08_tf,
    u8g2_font_helvR10_tf,
    u8g2_font_helvB10_tf,
    u8g2_font_profont10_tf
  };
  const char* names[] = {
    "u8g2 6x12", "u8g2 7x14", "helvR08", "helvR10", "helvB10", "profont10"
  };
  const char* lines[] = {
    "MUSIC", "Sweet", "Justin Bieber", "We keep moving forward",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "0123456789"
  };

  int y = 10;
  for (int f = 0; f < 6; f++) {
    u8g2gfx.setFont(fonts[f]);
    u8g2gfx.drawStr(4, y, names[f]);
    y += 12;
    for (int i = 0; i < 6; i++) {
      u8g2gfx.drawStr(4, y, lines[i]);
      y += 12;
      if (y > H - 10) { y = 10; sprite.fillScreen(ST77XX_BLACK); }
    }
    y += 6;
    if (y > H - 10) { y = 10; sprite.fillScreen(ST77XX_BLACK); }
  }

  // Transfer whole sprite
  tft.drawRGBBitmap(0, 0, sprite.getBuffer(), W, H);
}

void loop() {}