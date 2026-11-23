// ============================================================================
// RenderDiag - staged text-pipeline diagnostic for the ST7735 panel
// ============================================================================
// Five clean, full-screen tests. Each redraws the whole panel so nothing from a
// previous stage can be mistaken for corruption in the next one.
//
//   A  U8g2  -> TFT            (direct, no sprite)
//   B  U8g2  -> sprite -> TFT  (same sprite transfer as production)
//   C  GFX built-in font -> sprite -> TFT
//   D  4-bit AA font -> sprite -> TFT  (the production custom renderer, fixed)
//   E  old nibble parity (red) vs fixed parity (green), same font/data
//
// Stage E is the decisive one: both halves are produced from Inter_14.h with
// identical data; only the nibble-order test differs. If the red half is
// shredded while the green half is clean, the root cause is confirmed on the
// physical panel.
// ============================================================================
#include <Arduino.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <U8g2_for_Adafruit_GFX.h>
#include "Fonts/Inter_14.h"

#define TFT_CS   10
#define TFT_DC   13
#define TFT_RST  14
#define TFT_MOSI 11
#define TFT_SCLK 12
#define TFT_BL   15

#define W 128
#define H 160

Adafruit_ST7735 tft(TFT_CS, TFT_DC, TFT_RST);
GFXcanvas16 sprite(W, H);
U8G2_FOR_ADAFRUIT_GFX u8g2gfx;

static const char* LINES[] = {
  "MUSIC",
  "Sweet",
  "Justin Bieber",
  "We keep moving forward",
  "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
  "0123456789"
};
static const int N_LINES = 6;

static void tftHeader(const char* label) {
  tft.fillScreen(ST77XX_BLACK);
  tft.setFont();
  tft.setTextSize(1);
  tft.setTextColor(ST77XX_CYAN, ST77XX_BLACK);
  tft.setCursor(2, 2);
  tft.print(label);
}

static void spriteHeader(const char* label) {
  sprite.fillScreen(ST77XX_BLACK);
  sprite.setFont();            // reset to the built-in 1-bit font
  sprite.setTextSize(1);
  sprite.setTextColor(ST77XX_CYAN, ST77XX_BLACK);
  sprite.setCursor(2, 2);
  sprite.print(label);
}

// --- Test A: U8g2 straight to the panel --------------------------------
static void testA() {
  tftHeader("A U8G2 direct");
  u8g2gfx.begin(tft);
  u8g2gfx.setFontMode(1);
  u8g2gfx.setForegroundColor(ST77XX_WHITE);
  u8g2gfx.setBackgroundColor(ST77XX_BLACK);
  u8g2gfx.setFont(u8g2_font_helvR08_tf);
  int y = 22;
  for (int i = 0; i < N_LINES; i++) {
    u8g2gfx.drawStr(4, y, LINES[i]);
    y += 20;
  }
}

// --- Test B: U8g2 into the sprite, then the production transfer --------
static void testB() {
  spriteHeader("B U8G2 sprite");
  u8g2gfx.begin(sprite);
  u8g2gfx.setFontMode(1);
  u8g2gfx.setForegroundColor(ST77XX_WHITE);
  u8g2gfx.setBackgroundColor(ST77XX_BLACK);
  u8g2gfx.setFont(u8g2_font_helvR08_tf);
  int y = 22;
  for (int i = 0; i < N_LINES; i++) {
    u8g2gfx.drawStr(4, y, LINES[i]);
    y += 20;
  }
  tft.drawRGBBitmap(0, 0, sprite.getBuffer(), W, H);
}

// --- Test C: built-in GFX font through the sprite ----------------------
static void testC() {
  spriteHeader("C GFX builtin");
  sprite.setTextSize(1);
  sprite.setTextColor(ST77XX_WHITE, ST77XX_BLACK);
  int y = 20;
  for (int i = 0; i < N_LINES; i++) {
    sprite.setCursor(4, y);
    sprite.print(LINES[i]);
    y += 20;
  }
  tft.drawRGBBitmap(0, 0, sprite.getBuffer(), W, H);
}

// 4-bit AA renderer. `buggy` selects the old continuous-parity test so the
// two behaviours can be shown from the exact same font data.
static void drawAA4(GFXcanvas16& cv, int x, int y, const char* s,
                    const GFXfont* font, uint16_t col, bool buggy) {
  if (!font || !cv.getBuffer()) return;
  int16_t x1, y1;
  uint16_t w, h;
  cv.setFont(font);
  cv.setTextSize(1);
  cv.getTextBounds(s, 0, 0, &x1, &y1, &w, &h);
  int cursorX = x - x1;
  uint16_t* buf = cv.getBuffer();
  const int cw = cv.width();
  const int ch = cv.height();
  const uint8_t* bitmap = (const uint8_t*)font->bitmap;

  for (const char* p = s; *p; p++) {
    if (*p < font->first || *p > font->last) continue;
    const GFXglyph* g = &font->glyph[*p - font->first];
    const int stride = (g->width + 1) / 2;
    for (int row = 0; row < g->height; row++) {
      int sy = y + g->yOffset + row;
      if (sy < 0 || sy >= ch) continue;
      for (int c = 0; c < g->width; c++) {
        int sx = cursorX + g->xOffset + c;
        if (sx < 0 || sx >= cw) continue;
        uint8_t packed = bitmap[g->bitmapOffset + row * stride + (c >> 1)];
        bool high = buggy ? (((row * g->width + c) % 2) == 0) : ((c & 1) == 0);
        uint8_t gray = high ? ((packed >> 4) & 0x0F) : (packed & 0x0F);
        if (!gray) continue;
        uint16_t bgp = buf[sy * cw + sx];
        int r  = ((((bgp >> 11) & 0x1F) * (15 - gray)) + (((col >> 11) & 0x1F) * gray)) / 15;
        int g2 = ((((bgp >> 5)  & 0x3F) * (15 - gray)) + (((col >> 5)  & 0x3F) * gray)) / 15;
        int b  = ((((bgp)        & 0x1F) * (15 - gray)) + (((col)        & 0x1F) * gray)) / 15;
        buf[sy * cw + sx] = (uint16_t)((r << 11) | (g2 << 5) | b);
      }
    }
    cursorX += g->xAdvance;
  }
}

// Same renderer, but restricted to a horizontal window so it can be used for
// a scrolled title without bleeding past the layout column.
static void drawAA4Clip(GFXcanvas16& cv, int x, int y, const char* s,
                        const GFXfont* font, uint16_t col, int clipX0, int clipX1) {
  if (!font || !cv.getBuffer()) return;
  int16_t x1, y1;
  uint16_t w, h;
  cv.setFont(font);
  cv.setTextSize(1);
  cv.getTextBounds(s, 0, 0, &x1, &y1, &w, &h);
  int cursorX = x - x1;
  uint16_t* buf = cv.getBuffer();
  const int cw = cv.width();
  const int ch = cv.height();
  const uint8_t* bitmap = (const uint8_t*)font->bitmap;

  for (const char* p = s; *p; p++) {
    if (*p < font->first || *p > font->last) continue;
    const GFXglyph* g = &font->glyph[*p - font->first];
    const int stride = (g->width + 1) / 2;
    for (int row = 0; row < g->height; row++) {
      int sy = y + g->yOffset + row;
      if (sy < 0 || sy >= ch) continue;
      for (int c = 0; c < g->width; c++) {
        int sx = cursorX + g->xOffset + c;
        if (sx < 0 || sx >= cw || sx < clipX0 || sx > clipX1) continue;
        uint8_t packed = bitmap[g->bitmapOffset + row * stride + (c >> 1)];
        uint8_t gray = ((c & 1) == 0) ? ((packed >> 4) & 0x0F) : (packed & 0x0F);
        if (!gray) continue;
        uint16_t bgp = buf[sy * cw + sx];
        int r  = ((((bgp >> 11) & 0x1F) * (15 - gray)) + (((col >> 11) & 0x1F) * gray)) / 15;
        int g2 = ((((bgp >> 5)  & 0x3F) * (15 - gray)) + (((col >> 5)  & 0x3F) * gray)) / 15;
        int b  = ((((bgp)        & 0x1F) * (15 - gray)) + (((col)        & 0x1F) * gray)) / 15;
        buf[sy * cw + sx] = (uint16_t)((r << 11) | (g2 << 5) | b);
      }
    }
    cursorX += g->xAdvance;
  }
}

// --- Test D: fixed 4-bit AA renderer -----------------------------------
static void testD() {
  spriteHeader("D 4bit FIXED");
  drawAA4(sprite, 4,  36, "MUSIC",          &Inter_14, ST77XX_WHITE, false);
  drawAA4(sprite, 4,  58, "Sweet",          &Inter_14, ST77XX_WHITE, false);
  drawAA4(sprite, 4,  80, "Justin Bieber",  &Inter_14, ST77XX_WHITE, false);
  drawAA4(sprite, 4, 102, "We keep moving", &Inter_14, ST77XX_WHITE, false);
  drawAA4(sprite, 4, 124, "ABCDEFGHIJKLM",  &Inter_14, ST77XX_WHITE, false);
  drawAA4(sprite, 4, 146, "0123456789",     &Inter_14, ST77XX_WHITE, false);
  tft.drawRGBBitmap(0, 0, sprite.getBuffer(), W, H);
}

// --- Test E: old (red) vs new (green) ----------------------------------
static void testE() {
  spriteHeader("E OLD red / NEW green");
  drawAA4(sprite, 4,  34, "Sweet Bieber", &Inter_14, ST77XX_RED,   true);
  drawAA4(sprite, 4,  56, "MUSIC 0123",   &Inter_14, ST77XX_RED,   true);
  drawAA4(sprite, 4,  90, "Sweet Bieber", &Inter_14, ST77XX_GREEN, false);
  drawAA4(sprite, 4, 112, "MUSIC 0123",   &Inter_14, ST77XX_GREEN, false);
  tft.drawRGBBitmap(0, 0, sprite.getBuffer(), W, H);
}

// --- Test F: scrolled title through the clipped AA renderer ------------
static void testF() {
  const char* title = "This Is A Very Long Song Title That Must Scroll";
  int16_t x1, y1;
  uint16_t tw = 0, th = 0;
  sprite.setFont(&Inter_14);
  sprite.setTextSize(1);
  sprite.getTextBounds(title, 0, 0, &x1, &y1, &tw, &th);

  const int winX = 4, winW = 120;
  const int loop = (int)tw + 24;
  const unsigned long period = (unsigned long)loop * 30 + 1200;
  unsigned long t0 = millis();

  while (millis() - t0 < 12000) {
    spriteHeader("F marquee clip");
    unsigned long ph = (millis() - t0) % period;
    int off = ph < 1200 ? 0 : (int)((ph - 1200) / 30);
    for (int k = 0; k < 2; k++) {
      drawAA4Clip(sprite, winX - off + k * loop, 90, title, &Inter_14,
                  ST77XX_WHITE, winX, winX + winW - 1);
    }
    tft.drawRGBBitmap(0, 0, sprite.getBuffer(), W, H);
    delay(30);
  }
}

void setup() {
  pinMode(TFT_BL, OUTPUT);
  analogWrite(TFT_BL, 220);
  SPI.begin(TFT_SCLK, -1, TFT_MOSI, TFT_CS);
  tft.initR(INITR_GREENTAB);
  tft.setRotation(2);

  Serial.begin(115200);
  Serial.println();
  Serial.println("=== RENDER DIAG: A B C D E (8-12 s each) ===");

  delay(500);
  Serial.println("[A] U8G2 direct");        testA(); delay(8000);
  Serial.println("[B] U8G2 sprite");        testB(); delay(8000);
  Serial.println("[C] GFX builtin sprite"); testC(); delay(8000);
  Serial.println("[D] 4-bit AA FIXED");     testD(); delay(10000);
  Serial.println("[E] OLD(red) vs NEW(green)"); testE(); delay(10000);
  Serial.println("[F] clipped marquee scroll"); testF();
  Serial.println("=== DONE: stage F animation finished ===");
}

void loop() {}
