// ============================================================================
// ui_modern.h - modern TFT UI for DeskBuddy (Adafruit GFX / GFXcanvas16)
// ============================================================================
// Renders the whole 128x160 frame into a sprite, then pushes only the rows that
// changed. Replaces the old direct-draw TFT dashboard section of the sketch.
//
// Typography: everything uses Org_01 (7px line height) drawn at integer scales,
// because the FreeSans faces bundled with Adafruit_GFX are 22-29px tall and do
// not fit a panel this small.
//
//   F_REG   x1   7px   body / labels / footer
//   F_BOLD  x2  14px   titles, section heads, emphasis
//   F_BIG   x2  14px   values in rings / cards
//   F_HUGE  x3  21px   hero numbers (clock, timer, temperature)
//
// Layout grid (160px tall):
//   0..17    header        (title left, battery + link dot right)
//   20..137  content
//   140..156 footer        (page dots)
// ============================================================================
#pragma once

#include "Fonts/Org_01.h"
#include "Fonts/TomThumb.h"
#include "Fonts/Picopixel.h"
#include "Fonts/Tiny3x3a2pt7b.h"
#include "Fonts/Roboto_8.h"
#include "Fonts/Roboto_14.h"
#include "Fonts/Roboto_21.h"
#include "Fonts/Inter_8.h"
#include "Fonts/Inter_14.h"
#include "Fonts/Inter_21.h"
#include "Fonts/Montserrat_8.h"
#include "Fonts/Montserrat_14.h"
#include "Fonts/Montserrat_21.h"
#include "Fonts/JetBrainsMono_8.h"
#include "Fonts/JetBrainsMono_14.h"
#include "Fonts/JetBrainsMono_21.h"
#include <esp_heap_caps.h>

#define UI_W 128
#define UI_H 160
#define UI_FRAME_MS 40              // 25 fps, steady
#define UI_TRANSITION_MS 220

#ifndef UI_PROFILE
#define UI_PROFILE 0
#endif

#define UI_PI 3.14159265f
#define UI_HALF_PI 1.57079633f
#define UI_TWO_PI 6.28318531f
#define UI_COVER 52                 // album art size on the music page
#define UI_MQ_W 112
#define UI_MQ_H 12

// Font tokens (ints, so call sites stay unchanged)
#define F_REG  0
#define F_BOLD 1
#define F_BIG  2
#define F_HUGE 3

// Font face mode: 0=Org_01(pixel), 1=TomThumb(compact), 2=Picopixel, 3=Tiny3x3a,
// 4=Roboto, 5=Inter, 6=Montserrat, 7=JetBrainsMono
// Set by the `set_font` command from the web panel.
static uint8_t uiFontFaceMode = 0;
static bool    uiFontAA = false;  // true for 4-bit anti-aliased TTF fonts

// Per-element font faces for the music page (face mode 0..7).
static uint8_t uiMusicTitleFont = 5;      static bool uiMusicTitleAA = true;   // Inter
static uint8_t uiMusicArtistFont = 5;     static bool uiMusicArtistAA = true;
static uint8_t uiMusicActiveLyricFont = 4; static bool uiMusicActiveLyricAA = true; // Roboto
static uint8_t uiMusicUpcomingLyricFont = 4; static bool uiMusicUpcomingLyricAA = true;
static uint8_t uiMusicTimerFont = 7;      static bool uiMusicTimerAA = true;   // JetBrains Mono
static uint8_t uiMusicStatusFont = 0;     static bool uiMusicStatusAA = false;  // Pixel

static inline uint8_t _uiScaleSteps(uint8_t id) {
  switch (id) {
    case F_BOLD:
    case F_BIG:  return 2;
    case F_HUGE: return 3;
    default:     return 1;
  }
}

static inline const GFXfont* uiFace(uint8_t id) {
  uint8_t sc = _uiScaleSteps(id);
  // For TTF-converted fonts (modes 4-7), return pre-scaled font
  // instead of relying on setTextSize() which block-scales bitmap fonts.
  switch (uiFontFaceMode) {
    case 1: return &TomThumb;
    case 2: return &Picopixel;
    case 3: return &Tiny3x3a2pt7b;
    case 4: // Roboto
      return (sc == 1) ? &Roboto_8 : (sc == 2) ? &Roboto_14 : &Roboto_21;
    case 5: // Inter
      return (sc == 1) ? &Inter_8 : (sc == 2) ? &Inter_14 : &Inter_21;
    case 6: // Montserrat
      return (sc == 1) ? &Montserrat_8 : (sc == 2) ? &Montserrat_14 : &Montserrat_21;
    case 7: // JetBrainsMono
      return (sc == 1) ? &JetBrainsMono_8 : (sc == 2) ? &JetBrainsMono_14 : &JetBrainsMono_21;
    default: return &Org_01;
  }
}

static inline uint8_t uiScale(uint8_t id) {
  // For TTF-converted fonts (modes 4-7), don't scale (font is already right size)
  if (uiFontFaceMode >= 4) return 1;
  return _uiScaleSteps(id);
}

static inline int uiLineH(uint8_t id) {
  if (uiFontFaceMode >= 4) {
    const GFXfont* f = uiFace(id);
    return f->yAdvance;
  }
  return 7 * (int)uiScale(id);
}

// ----------------------------------------------------------------------------
// Core state
// ----------------------------------------------------------------------------
static float         uiDt = 0.033f;
static unsigned long uiNowMs = 0;
static unsigned long uiLastFrameMs = 0;
static int           uiLastKey = -1;

static uint16_t* uiPrevBuf = nullptr;   // snapshot of outgoing page
static uint16_t* uiCompBuf = nullptr;   // composed transition frame
static bool          uiTransActive = false;
static unsigned long uiTransStart = 0;
static int           uiTransDir = 1;

static uint16_t* uiCoverBig = nullptr;  // smoothed album art
static bool      uiCoverReady = false;
static uint16_t  uiCoverAccent = 0;
static bool      uiBgBlurred = false;

// ----------------------------------------------------------------------------
// Math / colour helpers
// ----------------------------------------------------------------------------
static inline float uiClamp(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }
static inline float uiClamp01(float v) { return uiClamp(v, 0.0f, 1.0f); }
static inline float uiEaseOut(float t) { t = 1.0f - uiClamp01(t); return 1.0f - t * t * t; }
static inline void  uiSmooth(float& cur, float target, float rate) {
  cur += (target - cur) * (1.0f - expf(-uiDt * rate));
}

// t = 0..255 : 0 -> a, 255 -> b
static inline uint16_t uiLerp(uint16_t a, uint16_t b, uint8_t t) {
  int ar = a >> 11, ag = (a >> 5) & 63, ab = a & 31;
  int br = b >> 11, bg = (b >> 5) & 63, bb = b & 31;
  int r = ar + ((br - ar) * t) / 255;
  int g = ag + ((bg - ag) * t) / 255;
  int l = ab + ((bb - ab) * t) / 255;
  return (uint16_t)((r << 11) | (g << 5) | l);
}
static inline void uiUnpack(uint16_t c, int& r, int& g, int& b) {
  r = ((c >> 11) << 3) | (c >> 13);
  g = (((c >> 5) & 63) << 2) | ((c >> 9) & 3);
  b = ((c & 31) << 3) | ((c & 31) >> 2);
}
static inline uint16_t uiPack(int r, int g, int b) {
  r = r < 0 ? 0 : (r > 255 ? 255 : r);
  g = g < 0 ? 0 : (g > 255 ? 255 : g);
  b = b < 0 ? 0 : (b > 255 ? 255 : b);
  return (uint16_t)(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3));
}

static inline uint16_t* uiFb() { return sprite.getBuffer(); }
static inline uint16_t uiCardCol()  { return uiLerp(theme.bg, theme.text, 20); }
static inline uint16_t uiTrackCol() { return uiLerp(theme.bg, theme.text, 46); }
static inline uint16_t uiFade(uint16_t c, float a) { return uiLerp(theme.bg, c, (uint8_t)(uiClamp01(a) * 255.0f)); }

static uint16_t uiLoadColor(float v) {
  if (v < 0) return theme.secondary;
  if (v <= 45) return theme.success;
  if (v <= 75) return uiLerp(theme.success, theme.warning, (uint8_t)((v - 45) / 30.0f * 255));
  if (v <= 90) return uiLerp(theme.warning, theme.danger, (uint8_t)((v - 75) / 15.0f * 255));
  return theme.danger;
}

static inline void uiPx(int x, int y, uint16_t c, uint8_t a) {
  if ((unsigned)x >= UI_W || (unsigned)y >= UI_H || a == 0) return;
  uint16_t* p = &uiFb()[y * UI_W + x];
  *p = (a == 255) ? c : uiLerp(*p, c, a);
}

// ----------------------------------------------------------------------------
// Anti-aliased shapes
// ----------------------------------------------------------------------------
static void uiAnnulus(float cx, float cy, float rOut, float rIn, uint16_t col, uint8_t alpha = 255) {
  if (rOut <= 0.0f) return;
  int x0 = (int)floorf(cx - rOut - 1), x1 = (int)ceilf(cx + rOut + 1);
  int y0 = (int)floorf(cy - rOut - 1), y1 = (int)ceilf(cy + rOut + 1);
  if (x0 < 0) x0 = 0; if (y0 < 0) y0 = 0;
  if (x1 > UI_W - 1) x1 = UI_W - 1;
  if (y1 > UI_H - 1) y1 = UI_H - 1;
  float lo = (rIn > 0) ? (rIn - 1.0f) : -1.0f;
  float lo2 = lo > 0 ? lo * lo : -1.0f, hi2 = (rOut + 1.0f) * (rOut + 1.0f);
  for (int y = y0; y <= y1; y++) {
    float dy = y + 0.5f - cy, dy2 = dy * dy;
    for (int x = x0; x <= x1; x++) {
      float dx = x + 0.5f - cx, d2 = dx * dx + dy2;
      if (d2 > hi2 || d2 < lo2) continue;
      float d = sqrtf(d2);
      float cov = rOut - d + 0.5f;
      if (rIn > 0) { float c2 = d - rIn + 0.5f; if (c2 < cov) cov = c2; }
      cov = uiClamp01(cov);
      if (cov > 0) uiPx(x, y, col, (uint8_t)(cov * alpha));
    }
  }
}
static inline void uiDisc(float cx, float cy, float r, uint16_t col, uint8_t alpha = 255) {
  uiAnnulus(cx, cy, r, 0, col, alpha);
}

// Progress arc with round caps. Sweeps clockwise from the top (+rot).
static void uiArc(float cx, float cy, float rMid, float th, float frac, uint16_t col,
                  uint8_t alpha = 255, float rot = 0.0f) {
  if (frac <= 0.0f || rMid <= 0.0f) return;
  frac = uiClamp01(frac);
  float rO = rMid + th * 0.5f, rI = rMid - th * 0.5f, cr = th * 0.5f;
  if (rI < 0.0f) rI = 0.0f;
  float sweep = frac * UI_TWO_PI;
  bool full = frac >= 0.999f;
  float a0 = -UI_HALF_PI + rot, a1 = a0 + sweep;
  float u0x = cosf(a0), u0y = sinf(a0), u1x = cosf(a1), u1y = sinf(a1);
  float c0x = cx + rMid * u0x, c0y = cy + rMid * u0y;
  float c1x = cx + rMid * u1x, c1y = cy + rMid * u1y;
  bool longSweep = sweep > UI_PI;
  int x0 = (int)floorf(cx - rO - 1), x1 = (int)ceilf(cx + rO + 1);
  int y0 = (int)floorf(cy - rO - 1), y1 = (int)ceilf(cy + rO + 1);
  if (x0 < 0) x0 = 0; if (y0 < 0) y0 = 0;
  if (x1 > UI_W - 1) x1 = UI_W - 1;
  if (y1 > UI_H - 1) y1 = UI_H - 1;
  float lo = rI - 1.0f; float lo2 = lo > 0 ? lo * lo : -1.0f, hi2 = (rO + 1.0f) * (rO + 1.0f);
  for (int y = y0; y <= y1; y++) {
    float py = y + 0.5f;
    for (int x = x0; x <= x1; x++) {
      float px = x + 0.5f;
      float dx = px - cx, dy = py - cy, d2 = dx * dx + dy * dy;
      if (d2 > hi2 || d2 < lo2) continue;
      float d = sqrtf(d2);
      float ring = uiClamp01(fminf(rO - d + 0.5f, d - rI + 0.5f));
      float cov = 0;
      if (full) cov = ring;
      else {
        bool inside;
        if (!longSweep) inside = (u0x * dy - u0y * dx) >= 0.0f && (dx * u1y - dy * u1x) >= 0.0f;
        else            inside = !((u1x * dy - u1y * dx) >= 0.0f && (dx * u0y - dy * u0x) >= 0.0f);
        if (inside) cov = ring;
        float e0 = uiClamp01(cr - sqrtf((px - c0x) * (px - c0x) + (py - c0y) * (py - c0y)) + 0.5f);
        float e1 = uiClamp01(cr - sqrtf((px - c1x) * (px - c1x) + (py - c1y) * (py - c1y)) + 0.5f);
        if (e0 > cov) cov = e0;
        if (e1 > cov) cov = e1;
      }
      if (cov > 0) uiPx(x, y, col, (uint8_t)(cov * alpha));
    }
  }
}

// Rounded rectangle with optional vertical gradient and 1px border.
// Corner inset is solved once per scanline (one sqrtf per row).
static void uiCard(float x, float y, float w, float h, float r, uint16_t fill,
                   uint16_t border, uint8_t borderA = 0, uint8_t fillA = 255,
                   uint16_t fill2 = 0, bool grad = false) {
  if (w <= 0.0f || h <= 0.0f) return;
  float hx = w * 0.5f, hy = h * 0.5f, cx = x + hx, cy = y + hy;
  if (r < 0.0f) r = 0.0f;
  if (r > hx) r = hx;
  if (r > hy) r = hy;
  int py0 = (int)floorf(y);      if (py0 < 0) py0 = 0;
  int py1 = (int)ceilf(y + h);   if (py1 > UI_H) py1 = UI_H;
  float band = hy - r;
  for (int py = py0; py < py1; py++) {
    float qy = py + 0.5f;
    float dy = fabsf(qy - cy) - band;
    float inset = 0.0f;
    if (dy > 0.0f) {
      if (dy >= r) continue;
      inset = r - sqrtf(r * r - dy * dy);
    }
    float xl = x + inset, xr = x + w - inset;
    if (xr <= xl) continue;
    uint16_t rowc = grad ? uiLerp(fill, fill2, (uint8_t)(uiClamp01((py - y) / h) * 255)) : fill;
    int px0 = (int)floorf(xl) - 1; if (px0 < 0) px0 = 0;
    int px1 = (int)ceilf(xr) + 1;  if (px1 > UI_W) px1 = UI_W;
    for (int px = px0; px < px1; px++) {
      float qx = px + 0.5f;
      float d = fmaxf(xl - qx, qx - xr);
      float cov = 0.5f - d;
      if (cov <= 0.0f) continue;
      if (cov > 1.0f) cov = 1.0f;
      uint16_t c = rowc;
      if (borderA && d > -1.0f) c = uiLerp(c, border, (uint8_t)(uiClamp01(d + 1.0f) * borderA));
      uiPx(px, py, c, (uint8_t)(cov * fillA));
    }
  }
}
static inline void uiPanel(float x, float y, float w, float h, float r = 6) {
  uiCard(x, y, w, h, r, uiCardCol(), theme.text, 40);
}

// ----------------------------------------------------------------------------
// Text
// ----------------------------------------------------------------------------
static void uiClean(char* dst, size_t sz, const char* src) {
  size_t n = 0; bool skipped = false;
  if (!src || sz == 0) { if (sz) dst[0] = 0; return; }
  for (; *src && n + 1 < sz; src++) {
    uint8_t c = (uint8_t)*src;
    if (c >= 0x20 && c < 0x7F) { dst[n++] = (char)c; skipped = false; }
    else if (c >= 0x80 && !skipped && n + 1 < sz) { if ((c & 0xC0) != 0x80) { dst[n++] = '?'; skipped = true; } }
  }
  dst[n] = 0;
}

static int uiW(const char* s, uint8_t fid) {
  if (!s || !s[0]) return 0;
  // For TTF fonts (4-bit AA), measure using glyph xAdvance directly.
  // Must use uiFace(fid) (not uiFace(uiFontFaceMode)) so the scale matches
  // what uiTextAARect / uiText actually draw (e.g. F_HUGE => 21px glyphs).
  if (uiFontFaceMode >= 4) {
    const GFXfont* font = uiFace(fid);
    if (!font) return 0;
    int w = 0;
    for (const char* p = s; *p; p++) {
      if (*p < font->first || *p > font->last) continue;
      const GFXglyph* g = &font->glyph[*p - font->first];
      w += g->xAdvance;
    }
    return w * uiScale(fid);
  }
  int16_t x1, y1; uint16_t w, h;
  sprite.setFont(uiFace(uiFontFaceMode)); sprite.setTextSize(uiScale(fid));
  sprite.getTextBounds(s, 0, 0, &x1, &y1, &w, &h);
  return (int)w;
}
// align: 0 left, 1 centre, 2 right. y is the text baseline.
static void uiText(int x, int y, const char* s, uint8_t fid, uint16_t col, int align);

// Draws 4-bit anti-aliased glyphs into any GFXcanvas16, optionally clipped to
// a horizontal window [clipX0, clipX1]. y is the text baseline. The canvas
// dimensions are queried from the object so this works for the main sprite and
// for the marquee target alike.
static void uiTextAARect(GFXcanvas16* cv, int x, int y, const char* s, uint8_t fid,
                         uint16_t col, int align, int clipX0, int clipX1) {
  if (!cv || !s || !s[0]) return;
  const GFXfont* font = uiFace(fid);
  uint16_t* buf = cv->getBuffer();
  if (!font || !buf) return;
  const int cw = cv->width(), ch = cv->height();

  // Use Adafruit GFX to get text bounds for alignment.
  int16_t x1, y1; uint16_t w, h;
  cv->setFont(font); cv->setTextSize(1); cv->setTextColor(col);
  cv->getTextBounds(s, 0, 0, &x1, &y1, &w, &h);
  int px = (align == 0) ? x - x1 : (align == 1 ? x - (int)w / 2 - x1 : x - (int)w - x1);

  int cursorX = px;
  uint16_t fg = col;
  uint8_t* bitmap = (uint8_t*)font->bitmap;

  for (const char* p = s; *p; p++) {
    if (*p < font->first || *p > font->last) continue;
    GFXglyph* g = (GFXglyph*)&font->glyph[*p - font->first];
    uint8_t gw = g->width;
    uint8_t gh = g->height;
    int8_t xo = g->xOffset;
    int8_t yo = g->yOffset;
    uint16_t bo = g->bitmapOffset;
    uint8_t xa = g->xAdvance;

    if (gw > 0 && gh > 0) {
      // Each row is padded to a whole byte by font_converter_aa.py, so the
      // nibble order restarts at every row: even column => high nibble.
      const int stride = (gw + 1) / 2;
      for (int row = 0; row < gh; row++) {
        int sy = y + yo + row;
        if (sy < 0 || sy >= ch) continue;
        for (int c = 0; c < gw; c++) {
          int sx = cursorX + xo + c;
          if (sx < 0 || sx >= cw || sx < clipX0 || sx > clipX1) continue;
          uint8_t packed = bitmap[bo + row * stride + (c >> 1)];
          uint8_t gray = (c & 1) ? (packed & 0x0F) : ((packed >> 4) & 0x0F);
          if (!gray) continue;

          uint16_t bgp = buf[sy * cw + sx];
          int r  = (((bgp >> 11) & 0x1F) * (15 - gray) + ((fg >> 11) & 0x1F) * gray) / 15;
          int g2 = (((bgp >> 5)  & 0x3F) * (15 - gray) + ((fg >> 5)  & 0x3F) * gray) / 15;
          int b  = (( bgp        & 0x1F) * (15 - gray) + ( fg        & 0x1F) * gray) / 15;
          buf[sy * cw + sx] = (uint16_t)((r << 11) | (g2 << 5) | b);
        }
      }
    }
    cursorX += xa;
  }
}

static void uiTextAA(int x, int y, const char* s, uint8_t fid, uint16_t col, int align = 0) {
  if (!s || !s[0]) return;
  const GFXfont* font = uiFace(fid);
  if (!font) { uiText(x, y, s, fid, col, align); return; }
  uiTextAARect(&sprite, x, y, s, fid, col, align, 0, UI_W - 1);
}

static void uiText(int x, int y, const char* s, uint8_t fid, uint16_t col, int align = 0) {
  if (!s || !s[0]) return;
  // TTF fonts (mode >= 4) are 4-bit AA; use uiTextAA for them.
  // Pixel fonts (mode 0-3) are 1-bit; use sprite.print for them.
  // uiFontAA flag is ignored for Pixel fonts (they don't support AA).
  if (uiFontFaceMode >= 4) {
    uiTextAA(x, y, s, fid, col, align);
    return;
  }
  int16_t x1, y1; uint16_t w, h;
  sprite.setFont(uiFace(uiFontFaceMode)); sprite.setTextSize(uiScale(fid)); sprite.setTextColor(col);
  sprite.getTextBounds(s, 0, 0, &x1, &y1, &w, &h);
  int px = (align == 0) ? x - x1 : (align == 1 ? x - (int)w / 2 - x1 : x - (int)w - x1);
  sprite.setCursor(px, y);
  sprite.print(s);
}
static void uiFit(char* out, size_t sz, const char* s, uint8_t fid, int maxW) {
  uiClean(out, sz, s);
  if (uiW(out, fid) <= maxW) return;
  int n = strlen(out);
  while (n > 1) {
    out[--n] = 0;
    char t[100]; snprintf(t, sizeof(t), "%s..", out);
    if (uiW(t, fid) <= maxW) { strncpy(out, t, sz - 1); out[sz - 1] = 0; return; }
  }
}
static void uiTextFit(int x, int y, const char* s, uint8_t fid, uint16_t col, int maxW, int align = 0) {
  char t[100]; uiFit(t, sizeof(t), s, fid, maxW); uiText(x, y, t, fid, col, align);
}

// Scrolls long text inside a clipped window; short text is drawn in place.
static GFXcanvas16* uiMq = nullptr;
static void uiMarquee(int x, int baseline, int w, const char* s, uint8_t fid,
                      uint16_t col, uint16_t bg, bool center) {
  char t[100]; uiClean(t, sizeof(t), s);
  int tw = uiW(t, fid);
  uint8_t sc = uiScale(fid);
  if (tw <= w) { uiText(center ? x + w / 2 : x, baseline, t, fid, col, center ? 1 : 0); return; }
  // 4-bit AA fonts must never go through the 1-bit GFXcanvas16 print() path
  // below (it reads 4-bit glyph data as a 1-bit bitmap and scatters it).
  // Scroll them straight into the framebuffer under a clipped window instead.
  if (uiFontFaceMode >= 4) {
    int loop = tw + 24;
    unsigned long period = (unsigned long)loop * 30 + 1200, ph = uiNowMs % period;
    int off = ph < 1200 ? 0 : (int)((ph - 1200) / 30);
    for (int k = 0; k < 2; k++) {
      uiTextAARect(&sprite, x - off + k * loop, baseline, t, fid, col, 0, x, x + w - 1);
    }
    return;
  }
  if (!uiMq) uiMq = new GFXcanvas16(UI_MQ_W, UI_MQ_H);
  if (!uiMq || !uiMq->getBuffer() || w > UI_MQ_W) { uiTextFit(x, baseline, t, fid, col, w); return; }
  uiMq->fillScreen(bg);
  uiMq->setFont(uiFace(fid)); uiMq->setTextSize(sc); uiMq->setTextColor(col);
  int loop = tw + 24;
  unsigned long period = (unsigned long)loop * 30 + 1200, ph = uiNowMs % period;
  int off = ph < 1200 ? 0 : (int)((ph - 1200) / 30);
  int16_t x1, y1; uint16_t bw, bh;
  uiMq->getTextBounds(t, 0, 0, &x1, &y1, &bw, &bh);
  int base = UI_MQ_H - 1;
  for (int k = 0; k < 2; k++) { uiMq->setCursor(-x1 - off + k * loop, base); uiMq->print(t); }
  uint16_t* b = uiMq->getBuffer();
  for (int row = 0; row < UI_MQ_H; row++) {
    uint16_t* r = b + row * UI_MQ_W;
    for (int i = 0; i < 3; i++) {
      uint8_t a = (uint8_t)((i + 1) * 255 / 4);
      r[i] = uiLerp(bg, r[i], a);
      r[w - 1 - i] = uiLerp(bg, r[w - 1 - i], a);
    }
    sprite.drawRGBBitmap(x, baseline - UI_MQ_H + 1 + row, r, w, 1);
  }
}

// Word wrap by pixel width. Returns line count.
static int uiWrap(const char* s, uint8_t fid, int maxW, char out[][40], int maxLines) {
  char t[128]; uiClean(t, sizeof(t), s);
  int len = strlen(t), pos = 0, n = 0; char buf[40];
  while (pos < len && n < maxLines) {
    while (t[pos] == ' ') pos++;
    if (pos >= len) break;
    int lastFit = -1;
    for (int i = pos; i <= len; i++) {
      if (t[i] == ' ' || t[i] == '\0') {
        int l = i - pos; if (l > 39) l = 39;
        memcpy(buf, t + pos, l); buf[l] = 0;
        if (uiW(buf, fid) <= maxW) lastFit = i; else break;
        if (t[i] == '\0') break;
      }
    }
    if (lastFit < 0) {
      int l = 0;
      while (pos + l < len && l < 38) {
        memcpy(buf, t + pos, l + 1); buf[l + 1] = 0;
        if (uiW(buf, fid) > maxW) break; l++;
      }
      if (l < 1) l = 1;
      lastFit = pos + l;
    }
    int l = lastFit - pos; if (l > 39) l = 39;
    memcpy(out[n], t + pos, l); out[n][l] = 0;
    // Hard guarantee: a line can never be wider than the window, whatever the
    // wrapping path produced.
    uiFit(out[n], 40, out[n], fid, maxW);
    n++;
    pos = lastFit;
  }
  while (pos < len && t[pos] == ' ') pos++;
  if (pos < len && n > 0) {
    char tmp[44]; snprintf(tmp, sizeof(tmp), "%.37s..", out[n - 1]);
    uiFit(out[n - 1], 40, tmp, fid, maxW);
  }
  return n;
}

static void uiFmtTime(int sec, char* buf, size_t sz) {
  if (sec < 0) sec = 0;
  snprintf(buf, sz, "%d:%02d", sec / 60, sec % 60);
}

// ----------------------------------------------------------------------------
// Background + small widgets
// ----------------------------------------------------------------------------
static uint16_t* uiBgCache = nullptr;
static uint32_t  uiBgKey = 0xFFFFFFFF;

static void uiBackground(uint16_t glow, uint8_t amt = 34) {
  const bool wp = hasWallpaper && wallpaperBuf != nullptr;
  uint32_t key = wp
      ? (0xB0000000u ^ ((uint32_t)wallpaperVersion * 2654435761u)
         ^ ((uint32_t)theme.bg << 16) ^ ((uint32_t)wallpaperOpacity << 4) ^ amt)
      : (((uint32_t)theme.bg << 16) ^ ((uint32_t)glow << 3) ^ amt);
  if (!uiBgCache) {
    uiBgCache = (uint16_t*)heap_caps_malloc(UI_W * UI_H * sizeof(uint16_t), MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    if (!uiBgCache) uiBgCache = (uint16_t*)malloc(UI_W * UI_H * sizeof(uint16_t));
    uiBgKey = 0xFFFFFFFF;
  }
  if (uiBgCache && key != uiBgKey) {
    for (int y = 0; y < UI_H; y++) {
      uint16_t* r = uiBgCache + y * UI_W;
      if (wp) {
        const uint16_t* s = wallpaperBuf + y * UI_W;
        // Extra scrim behind the header keeps the title readable on busy art.
        int extra = y < 20 ? 16 : 0;
        uint8_t dark = (uint8_t)constrain((int)wallpaperOpacity + extra, 0, 255);
        for (int x = 0; x < UI_W; x++) r[x] = uiLerp(s[x], theme.bg, dark);
      } else {
        uint16_t c = theme.bg;
        if (y < 72) { float k = 1.0f - y / 72.0f; c = uiLerp(theme.bg, glow, (uint8_t)(amt * k * k)); }
        for (int x = 0; x < UI_W; x++) r[x] = c;
      }
    }
    uiBgKey = key;
  }
  if (uiBgCache) { memcpy(uiFb(), uiBgCache, UI_W * UI_H * sizeof(uint16_t)); return; }
  for (int y = 0; y < UI_H; y++) {
    uint16_t* r = uiFb() + y * UI_W;
    if (wp) {
      const uint16_t* s = wallpaperBuf + y * UI_W;
      for (int x = 0; x < UI_W; x++) r[x] = uiLerp(s[x], theme.bg, wallpaperOpacity);
    } else {
      uint16_t c = theme.bg;
      if (y < 72) { float k = 1.0f - y / 72.0f; c = uiLerp(theme.bg, glow, (uint8_t)(amt * k * k)); }
      for (int x = 0; x < UI_W; x++) r[x] = c;
    }
  }
}

static void uiBatteryIcon(int x, int y) {
  int pct = batteryPercent();
  if (pct == -1) return;
  uiCard(x, y, 16, 8, 2, uiCardCol(), theme.text, 110);
  sprite.fillRect(x + 16, y + 2, 2, 4, uiLerp(theme.bg, theme.text, 110));
  if (pct == -2) {
    uiCard(x + 2, y + 2, 12, 4, 1, theme.success, theme.success, 0);
  } else if (pct >= 0) {
    uint16_t c = pct < 20 ? theme.danger : (pct < 50 ? theme.warning : theme.success);
    int fw = (pct * 12) / 100; if (fw < 2 && pct > 0) fw = 2;
    if (fw > 0) uiCard(x + 2, y + 2, fw, 4, 1, c, c, 0);
  }
}

// Header: title on the left, battery + link state on the right.
static void uiTopBar(const char* title) {
  uiCard(0, 0, UI_W, 18, 0, uiLerp(theme.bg, theme.text, 10), theme.text, 0);
  uiTextFit(6, 13, title, F_REG, theme.secondary, 74);
  uiBatteryIcon(92, 5);
  uint16_t lc = state.backendOnline ? theme.success : theme.danger;
  uiDisc(121, 9.0f, 2.6f, lc);
  if (state.backendOnline) {
    float ph = fmodf(uiNowMs / 1800.0f, 1.0f);
    uiAnnulus(121, 9.0f, 2.6f + ph * 5.0f, 2.6f + ph * 5.0f - 1.0f, lc, (uint8_t)((1.0f - ph) * 160));
  }
}

static float uiPageF = 0;
static void uiPageDots() {
  const int n = PAGE_COUNT, gap = 10, y = 151;
  uiSmooth(uiPageF, (float)page, 14.0f);
  int x0 = 64 - ((n - 1) * gap) / 2;
  for (int i = 0; i < n; i++) uiDisc(x0 + i * gap, y, 1.5f, theme.secondary, 120);
  uiCard(x0 + uiPageF * gap - 5, y - 1.5f, 10, 3, 1.5f, theme.accent, theme.accent, 0);
}

static int uiPill(int x, int y, int h, const char* s, uint8_t fid, uint16_t fg, uint16_t bgc, int padX = 7) {
  int tw = uiW(s, fid), w = tw + padX * 2;
  uiCard(x, y, w, h, h / 2.0f, bgc, fg, 0);
  uiText(x + padX, y + h - (h - uiLineH(fid)) / 2 - 1, s, fid, fg);
  return w;
}

static void uiChip(int x, int y, int w, uint16_t dot, const char* s) {
  uiPanel(x, y, w, 16, 8);
  uiDisc(x + 8, y + 8, 2.2f, dot);
  uiTextFit(x + 14, y + 12, s, F_REG, theme.text, w - 18);
}

static void uiEq(int x, int baseY, int n, uint16_t col, bool playing) {
  for (int i = 0; i < n; i++) {
    float h = playing ? 2.0f + (0.5f + 0.5f * sinf(uiNowMs / 170.0f + i * 1.7f)) * 6.0f : 2.0f;
    uiCard(x + i * 4, baseY - h, 2, h, 1.0f, col, col, 0);
  }
}

static void uiNoteGlyph(float x, float y, uint16_t col) {
  uiDisc(x, y, 2.5f, col);
  sprite.fillRect((int)x + 2, (int)y - 9, 2, 9, col);
  sprite.fillRect((int)x + 2, (int)y - 9, 5, 3, col);
}

// ----------------------------------------------------------------------------
// Cover art processing (called from the serial handlers)
// ----------------------------------------------------------------------------
void uiOnCoverThumb() {
  if (!coverThumb) return;
  if (!uiCoverBig) {
    size_t sz = UI_COVER * UI_COVER * sizeof(uint16_t);
    uiCoverBig = (uint16_t*)(psramFound() ? ps_malloc(sz) : malloc(sz));
  }
  if (!uiCoverBig) return;
  const int sw = COVER_THUMB_W, sh = COVER_THUMB_H;
  for (int y = 0; y < UI_COVER; y++) {
    float v = (y + 0.5f) * sh / UI_COVER - 0.5f;
    int v0 = (int)floorf(v); float fv = v - v0;
    int v1 = v0 + 1; if (v0 < 0) v0 = 0; if (v1 > sh - 1) v1 = sh - 1;
    for (int x = 0; x < UI_COVER; x++) {
      float u = (x + 0.5f) * sw / UI_COVER - 0.5f;
      int u0 = (int)floorf(u); float fu = u - u0;
      int u1 = u0 + 1; if (u0 < 0) u0 = 0; if (u1 > sw - 1) u1 = sw - 1;
      int r[4], g[4], b[4];
      uiUnpack(coverThumb[v0 * sw + u0], r[0], g[0], b[0]);
      uiUnpack(coverThumb[v0 * sw + u1], r[1], g[1], b[1]);
      uiUnpack(coverThumb[v1 * sw + u0], r[2], g[2], b[2]);
      uiUnpack(coverThumb[v1 * sw + u1], r[3], g[3], b[3]);
      float w0 = (1 - fu) * (1 - fv), w1 = fu * (1 - fv), w2 = (1 - fu) * fv, w3 = fu * fv;
      uiCoverBig[y * UI_COVER + x] = uiPack((int)(r[0] * w0 + r[1] * w1 + r[2] * w2 + r[3] * w3),
                                           (int)(g[0] * w0 + g[1] * w1 + g[2] * w2 + g[3] * w3),
                                           (int)(b[0] * w0 + b[1] * w1 + b[2] * w2 + b[3] * w3));
    }
  }
  // dominant colour, weighted by saturation
  float sr = 0, sg = 0, sb = 0, sw2 = 0;
  for (int i = 0; i < sw * sh; i++) {
    int r, g, b; uiUnpack(coverThumb[i], r, g, b);
    int mx = max(r, max(g, b)), mn = min(r, min(g, b));
    float wgt = (float)(mx - mn); wgt = wgt * wgt + 1.0f;
    sr += r * wgt; sg += g * wgt; sb += b * wgt; sw2 += wgt;
  }
  uiCoverAccent = 0;
  if (sw2 > 0) {
    float r = sr / sw2, g = sg / sw2, b = sb / sw2, mx = fmaxf(r, fmaxf(g, b));
    float satSpan = mx - fminf(r, fminf(g, b));
    if (mx > 8 && satSpan > 24) {
      float k = fminf(230.0f / mx, 2.4f);
      uiCoverAccent = uiPack((int)(r * k), (int)(g * k), (int)(b * k));
    }
  }
  uiCoverReady = true;
}

// Blur + darken the lyrics background. Done at 32x40 (a clean 4x downscale of
// the 128x160 buffer) so the whole operation is a few thousand taps instead of
// half a million, then bilinearly upscaled. Runs in well under a millisecond.
void uiOnCoverBg() {
  if (!lyricsBg) return;
  static uint16_t small[32 * 40];
  static uint16_t tmp[32 * 40];
  const int SW = 32, SH = 40;

  for (int y = 0; y < SH; y++) {
    for (int x = 0; x < SW; x++) {
      int r = 0, g = 0, b = 0;
      for (int dy = 0; dy < 4; dy++) {
        const uint16_t* row = lyricsBg + (y * 4 + dy) * TFT_W + x * 4;
        for (int dx = 0; dx < 4; dx++) {
          int rr, gg, bb; uiUnpack(row[dx], rr, gg, bb);
          r += rr; g += gg; b += bb;
        }
      }
      small[y * SW + x] = uiPack(r / 16, g / 16, b / 16);
    }
  }
  const int R = 2;
  for (int y = 0; y < SH; y++) {
    for (int x = 0; x < SW; x++) {
      int r = 0, g = 0, b = 0, n = 0;
      for (int k = -R; k <= R; k++) {
        int xx = x + k; if (xx < 0) xx = 0; if (xx > SW - 1) xx = SW - 1;
        int rr, gg, bb; uiUnpack(small[y * SW + xx], rr, gg, bb);
        r += rr; g += gg; b += bb; n++;
      }
      tmp[y * SW + x] = uiPack(r / n, g / n, b / n);
    }
  }
  for (int y = 0; y < SH; y++) {
    for (int x = 0; x < SW; x++) {
      int r = 0, g = 0, b = 0, n = 0;
      for (int k = -R; k <= R; k++) {
        int yy = y + k; if (yy < 0) yy = 0; if (yy > SH - 1) yy = SH - 1;
        int rr, gg, bb; uiUnpack(tmp[yy * SW + x], rr, gg, bb);
        r += rr; g += gg; b += bb; n++;
      }
      small[y * SW + x] = uiLerp(uiPack(r / n, g / n, b / n), theme.bg, 168);
    }
  }
  for (int y = 0; y < TFT_H; y++) {
    float v = (y + 0.5f) / 4.0f - 0.5f;
    int v0 = (int)floorf(v); if (v0 < 0) v0 = 0;
    int v1 = v0 + 1; if (v1 > SH - 1) v1 = SH - 1;
    float fv = v - v0;
    uint16_t* drow = lyricsBg + y * TFT_W;
    const uint16_t* r0 = small + v0 * SW;
    const uint16_t* r1 = small + v1 * SW;
    for (int x = 0; x < TFT_W; x++) {
      float u = (x + 0.5f) / 4.0f - 0.5f;
      int u0 = (int)floorf(u); if (u0 < 0) u0 = 0;
      int u1 = u0 + 1; if (u1 > SW - 1) u1 = SW - 1;
      float fu = u - u0;
      int r[4], g[4], b[4];
      uiUnpack(r0[u0], r[0], g[0], b[0]);
      uiUnpack(r0[u1], r[1], g[1], b[1]);
      uiUnpack(r1[u0], r[2], g[2], b[2]);
      uiUnpack(r1[u1], r[3], g[3], b[3]);
      float w0 = (1 - fu) * (1 - fv), w1 = fu * (1 - fv), w2 = (1 - fu) * fv, w3 = fu * fv;
      drow[x] = uiPack((int)(r[0] * w0 + r[1] * w1 + r[2] * w2 + r[3] * w3),
                       (int)(g[0] * w0 + g[1] * w1 + g[2] * w2 + g[3] * w3),
                       (int)(b[0] * w0 + b[1] * w1 + b[2] * w2 + b[3] * w3));
    }
  }
  uiBgBlurred = true;
}

// ----------------------------------------------------------------------------
// Home
// ----------------------------------------------------------------------------
static void uiNowPlayingCard(int y) {
  uiPanel(8, y, 112, 18, 8);
  if (state.musicTitle[0]) {
    uiEq(16, y + 13, 3, state.musicPlaying ? theme.success : theme.secondary, state.musicPlaying);
    uiMarquee(31, y + 12, 84, state.musicTitle, F_REG,
              state.musicPlaying ? theme.text : theme.secondary, uiCardCol(), false);
  } else {
    uiNoteGlyph(19, y + 12, theme.secondary);
    uiText(31, y + 12, "No music", F_REG, theme.secondary);
  }
}

void drawHome() {
  uiBackground(theme.accent);
  uiTopBar("DeskBuddy");

  // clock with a softly pulsing colon
  const char* clk = state.clockText[0] ? state.clockText : "--:--";
  char hh[8] = "--", mm[8] = "--";
  const char* colon = strchr(clk, ':');
  if (colon) {
    size_t n = colon - clk; if (n > 5) n = 5;
    memcpy(hh, clk, n); hh[n] = 0;
    strncpy(mm, colon + 1, 5); mm[5] = 0;
  }
  int wH = uiW(hh, F_HUGE), wC = uiW(":", F_HUGE), wM = uiW(mm, F_HUGE);
  int total = wH + wC + wM + 6;
  int x = 64 - total / 2;
  uiText(x, 46, hh, F_HUGE, theme.text);
  float pulse = 0.35f + 0.65f * (0.5f + 0.5f * sinf(uiNowMs / 320.0f));
  uiText(x + wH + 3, 44, ":", F_HUGE, uiFade(theme.accent, pulse));
  uiText(x + wH + wC + 6, 46, mm, F_HUGE, theme.text);

  if (state.unread > 0) {
    float pr = 1.0f + 0.10f * sinf(uiNowMs / 260.0f);
    uiDisc(112, 34, 8.0f * pr, theme.warning);
    char n[6]; snprintf(n, sizeof(n), "%d", state.unread > 9 ? 9 : state.unread);
    uiText(112, 37, n, F_REG, theme.bg, 1);
  }

  char dl[40];
  snprintf(dl, sizeof(dl), "%s %s", state.dowText, state.dateText[0] ? state.dateText : "--");
  uiTextFit(64, 60, dl, F_REG, theme.secondary, 112, 1);

  const char* act = activityLabel();
  if (act[0]) uiPill(8, 66, 15, act, F_REG, theme.warning, uiLerp(theme.bg, theme.warning, 48), 7);

  uiTextFit(8, 94, state.appName[0] ? state.appName : "Waiting for PC...", F_REG, theme.text, 112);

  char t[16], h[16];
  if (isnan(sensors.temperature)) snprintf(t, sizeof(t), "--.-C"); else snprintf(t, sizeof(t), "%.1fC", sensors.temperature);
  if (isnan(sensors.humidity)) snprintf(h, sizeof(h), "--%%"); else snprintf(h, sizeof(h), "%.0f%%", sensors.humidity);
  uiChip(8, 100, 54, theme.accent, t);
  uiChip(66, 100, 54, theme.success, h);

  uiNowPlayingCard(122);
  uiPageDots();
}

// ----------------------------------------------------------------------------
// Music
// ----------------------------------------------------------------------------
static float uiPlayT = 1.0f, uiProg = 0.0f;
static unsigned long uiProgressCompleteMs = 0;
static char  uiLastTitle[64] = "";

void drawMusicPage() {
  uint16_t accent = (uiCoverAccent && state.musicTitle[0]) ? uiCoverAccent : theme.accent;
  uint8_t savedFace = uiFontFaceMode;
  bool savedAA = uiFontAA;
  uint16_t* fb = uiFb();

  // --- FFT visualizer as full-page background ---
  for (int i = 0; i < UI_W * UI_H; i++) fb[i] = theme.bg;

  // Draw vertical bars for each FFT bin across the whole page.
  int barW = UI_W / FFT_BARS;
  if (barW < 1) barW = 1;
  for (int b = 0; b < FFT_BARS; b++) {
    float v = fftBins[b];
    if (v < 0.0f) v = 0.0f;
    if (v > 1.0f) v = 1.0f;
    int h = (int)(v * (UI_H - 6));
    if (h < 2) h = 2;
    int x0 = b * barW;
    int x1 = x0 + barW - 1;
    if (x1 >= UI_W) x1 = UI_W - 1;
    bool beat = fftBeat && (millis() - fftBeatMs < 120);
    for (int x = x0; x <= x1; x++) {
      for (int y = UI_H - 1; y >= UI_H - h; y--) {
        float t = (float)(UI_H - 1 - y) / (float)(h > 1 ? h : 1);
        uint8_t alpha = (uint8_t)(50 + 170 * t);
        if (beat) alpha = 255;
        uint16_t col = uiLerp(theme.bg, accent, alpha);
        int idx = y * UI_W + x;
        fb[idx] = uiLerp(fb[idx], col, beat ? 220 : 170);
      }
    }
  }

  // Light "blur": horizontal smear of each row.
  static uint16_t blurRow[UI_W];
  for (int y = 0; y < UI_H; y++) {
    for (int x = 0; x < UI_W; x++) {
      uint16_t c0 = fb[y * UI_W + (x > 0 ? x - 1 : x)];
      uint16_t c1 = fb[y * UI_W + x];
      uint16_t c2 = fb[y * UI_W + (x < UI_W - 1 ? x + 1 : x)];
      // average RGB565 via channel split
      uint8_t r0 = (c0 >> 11) & 0x1F, g0 = (c0 >> 5) & 0x3F, b0 = c0 & 0x1F;
      uint8_t r1 = (c1 >> 11) & 0x1F, g1 = (c1 >> 5) & 0x3F, b1 = c1 & 0x1F;
      uint8_t r2 = (c2 >> 11) & 0x1F, g2 = (c2 >> 5) & 0x3F, b2 = c2 & 0x1F;
      uint8_t rr = (r0 + r1 * 2 + r2) >> 2;
      uint8_t gg = (g0 + g1 * 2 + g2) >> 2;
      uint8_t bb = (b0 + b1 * 2 + b2) >> 2;
      blurRow[x] = (rr << 11) | (gg << 5) | bb;
    }
    memcpy(&fb[y * UI_W], blurRow, UI_W * sizeof(uint16_t));
  }

  // Readability scrim.
  for (int i = 0; i < UI_W * UI_H; i++) fb[i] = uiLerp(fb[i], theme.bg, 150);

  uiTopBar("Music");

  if (state.musicTitle[0] == '\0') {
    uiText(64, 70, "Nothing playing", F_BOLD, theme.text, 1);
    uiText(64, 86, "Open YouTube Music", F_REG, theme.secondary, 1);
    uiPageDots();
    return;
  }

  if (strcmp(uiLastTitle, state.musicTitle) != 0) {
    strncpy(uiLastTitle, state.musicTitle, sizeof(uiLastTitle) - 1);
    uiProg = -1;
  }

  uiSmooth(uiPlayT, state.musicPlaying ? 1.0f : 0.0f, 9.0f);

  // Cover art (small, top-left).
  const int C = 40;
  if (uiCoverReady && uiCoverBig) {
    for (int yy = 0; yy < C; yy++) {
      for (int xx = 0; xx < C; xx++) {
        int sx = xx * UI_COVER / C;
        int sy = yy * UI_COVER / C;
        uiPx(8 + xx, 22 + yy, uiCoverBig[sy * UI_COVER + sx], 255);
      }
    }
  } else {
    uiCard(8, 22, C, C, 6, uiLerp(theme.bg, accent, 70), accent, 60);
  }

  // Title + artist (TTF fonts with auto-AA, larger sizes for readability).
  uiFontFaceMode = uiMusicTitleFont; uiFontAA = true;
  // Use F_HUGE (21px) for title - clear and readable, with marquee for long text
  uiMarquee(52, 26, 74, state.musicTitle, F_HUGE, theme.text, theme.bg, true);
  uiFontFaceMode = uiMusicArtistFont; uiFontAA = true;
  // Artist marquees like the title.
  uiMarquee(52, 46, 74, state.musicArtist[0] ? state.musicArtist : "Unknown artist", F_REG, theme.secondary, theme.bg, true);

  // Current lyric (same font for all lines).
  if (state.musicPlaying && state.lyricCur[0] != '\0') {
    char ly[3][40];
    uiFontFaceMode = uiMusicActiveLyricFont; uiFontAA = uiMusicActiveLyricAA;
    int n = uiWrap(state.lyricCur, uiMusicActiveLyricFont, 112, ly, 3);
    uint16_t lcol = state.lyricsAvailable ? uiFade(accent, 0.95f) : uiFade(theme.text, 0.7f);
    int ly0 = 76;
    for (int i = 0; i < n; i++) {
      uiTextFit(8, ly0 + i * 11, ly[i], uiMusicActiveLyricFont, lcol, 112, 0);
    }
  }

  // Perimeter progress indicator around the album artwork.
  // Only advance when music is playing; freeze progress when paused.
  float target;
  if (!state.musicPlaying) {
    target = uiProg;  // freeze at current progress when paused
  } else if (state.musicDuration > 0) {
    target = uiClamp01((float)state.musicProgress / state.musicDuration);
  } else {
    target = 0.0f;
  }
  if (uiProg < 0) uiProg = 0.0f;
  // Reset on new track.
  if (strcmp(uiLastTitle, state.musicTitle) != 0) {
    strncpy(uiLastTitle, state.musicTitle, sizeof(uiLastTitle) - 1);
    uiLastTitle[sizeof(uiLastTitle) - 1] = 0;
    uiProg = 0.0f;
    uiProgressCompleteMs = 0;
  }
  uiSmooth(uiProg, target, 6.0f);
  if (uiProg > 0.999f) {
    uiProg = 1.0f;
    if (uiProgressCompleteMs == 0) uiProgressCompleteMs = millis();
  } else {
    uiProgressCompleteMs = 0;
  }

  // Artwork container (must match cover draw above).
  const int artX = 8, artY = 22, artW = 40, artH = 40;
  const int margin = 4;
  const int rx = artX - margin, ry = artY - margin;
  const int rw = artW + margin * 2, rh = artH + margin * 2;
  const int cr = 6; // corner radius

  // Configurable style (defaults).
  const uint16_t baseCol = 0x4208;   // dim blue/grey
  const uint16_t progCol = 0x3EDF;   // cyan #39D9FF
  const uint16_t glowCol = 0x1D9F;   // darker cyan glow
  const uint16_t endCol  = 0xFFFF;   // white leading endpoint
  const int borderThick = 2;
  const int glowLayers = 2;
  const int endSize = 3;

  // Perimeter length of rounded rect.
  float perim = 2.0f * (rw + rh) - 8.0f * cr + 2.0f * 3.14159265f * cr;

  // Helper lambda to get point along perimeter at distance s (0..perim).
  auto perimPoint = [&](float s, float* px, float* py) {
    // normalize
    while (s < 0) s += perim;
    while (s > perim) s -= perim;
    float cum = 0;
    // Segment lengths
    float lArc = 1.5707963f * cr; // quarter circle
    float lTop = (float)(rw - 2 * cr);
    float lRight = (float)(rh - 2 * cr);
    float lBottom = (float)(rw - 2 * cr);
    float lLeft = (float)(rh - 2 * cr);
    // 1: top-left arc (from left point to top point), clockwise
    if (s < lArc) {
      float a = 3.14159265f - (s / lArc) * 1.5707963f; // pi -> pi/2
      *px = (rx + cr) + cosf(a) * cr;
      *py = (ry + cr) + sinf(a) * cr;
      return;
    }
    cum += lArc;
    // 2: top edge
    if (s < cum + lTop) {
      float t = (s - cum) / (lTop > 0 ? lTop : 1);
      *px = (rx + cr) + t * lTop;
      *py = (float)ry;
      return;
    }
    cum += lTop;
    // 3: top-right arc
    if (s < cum + lArc) {
      float a = 1.5707963f - ((s - cum) / lArc) * 1.5707963f; // pi/2 -> 0
      *px = (rx + rw - cr) + cosf(a) * cr;
      *py = (ry + cr) + sinf(a) * cr;
      return;
    }
    cum += lArc;
    // 4: right edge
    if (s < cum + lRight) {
      float t = (s - cum) / (lRight > 0 ? lRight : 1);
      *px = (float)(rx + rw);
      *py = (ry + cr) + t * lRight;
      return;
    }
    cum += lRight;
    // 5: bottom-right arc
    if (s < cum + lArc) {
      float a = 0.0f - ((s - cum) / lArc) * 1.5707963f; // 0 -> -pi/2
      *px = (rx + rw - cr) + cosf(a) * cr;
      *py = (ry + rh - cr) + sinf(a) * cr;
      return;
    }
    cum += lArc;
    // 6: bottom edge
    if (s < cum + lBottom) {
      float t = (s - cum) / (lBottom > 0 ? lBottom : 1);
      *px = (rx + rw - cr) - t * lBottom;
      *py = (float)(ry + rh);
      return;
    }
    cum += lBottom;
    // 7: bottom-left arc
    if (s < cum + lArc) {
      float a = -1.5707963f - ((s - cum) / lArc) * 1.5707963f; // -pi/2 -> -pi
      *px = (rx + cr) + cosf(a) * cr;
      *py = (ry + rh - cr) + sinf(a) * cr;
      return;
    }
    cum += lArc;
    // 8: left edge
    {
      float t = (s - cum) / (lLeft > 0 ? lLeft : 1);
      *px = (float)rx;
      *py = (ry + rh - cr) - t * lLeft;
    }
  };

  // Draw base outline (full perimeter, dim). Smaller step + 2x2 brush for continuity.
  float step = 0.5f;
  for (float d = 0; d < perim; d += step) {
    float px, py;
    perimPoint(d, &px, &py);
    int ix = (int)(px + 0.5f);
    int iy = (int)(py + 0.5f);
    if (ix >= 0 && ix < UI_W && iy >= 0 && iy < UI_H) {
      uiPx(ix, iy, baseCol, 255);
      if (ix + 1 < UI_W) uiPx(ix + 1, iy, baseCol, 255);
      if (iy + 1 < UI_H) uiPx(ix, iy + 1, baseCol, 255);
      if (ix + 1 < UI_W && iy + 1 < UI_H) uiPx(ix + 1, iy + 1, baseCol, 255);
    }
  }

  // Draw progress segment.
  float progDist = perim * uiProg;
  // glow layers
  for (int g = glowLayers; g >= 1; g--) {
    uint8_t a = (uint8_t)(40 + 40 * (glowLayers - g + 1));
    for (float d = 0; d <= progDist; d += step) {
      float px, py;
      perimPoint(d, &px, &py);
      int ix = (int)(px + 0.5f);
      int iy = (int)(py + 0.5f);
      for (int oy = -g; oy <= g; oy++) {
        for (int ox = -g; ox <= g; ox++) {
          int x = ix + ox, y = iy + oy;
          if (x >= 0 && x < UI_W && y >= 0 && y < UI_H) {
            uiPx(x, y, glowCol, a);
          }
        }
      }
    }
  }
  // main progress line
  for (float d = 0; d <= progDist; d += step) {
    float px, py;
    perimPoint(d, &px, &py);
    int ix = (int)(px + 0.5f);
    int iy = (int)(py + 0.5f);
    for (int oy = 0; oy < borderThick; oy++) {
      for (int ox = 0; ox < borderThick; ox++) {
        int x = ix + ox, y = iy + oy;
        if (x >= 0 && x < UI_W && y >= 0 && y < UI_H) uiPx(x, y, progCol, 255);
      }
    }
  }

  // Leading endpoint.
  if (uiProg > 0.001f && uiProg < 0.999f) {
    float px, py;
    perimPoint(progDist, &px, &py);
    int ix = (int)(px + 0.5f);
    int iy = (int)(py + 0.5f);
    for (int dy = -endSize; dy <= endSize; dy++) {
      for (int dx = -endSize; dx <= endSize; dx++) {
        if (dx * dx + dy * dy <= endSize * endSize) {
          int x = ix + dx, y = iy + dy;
          if (x >= 0 && x < UI_W && y >= 0 && y < UI_H) {
            uiPx(x, y, endCol, 255);
          }
        }
      }
    }
  }

  // Completion hold: if complete, full perimeter already drawn (progDist=perim).

  char a[12], b[12]; uiFmtTime(state.musicProgress, a, sizeof(a)); uiFmtTime(state.musicDuration, b, sizeof(b));
  uiFontFaceMode = uiMusicTimerFont; uiFontAA = true;
  uiText(8, 106, a, F_REG, theme.secondary, 0);
  uiText(120, 106, b, F_REG, theme.secondary, 2);

  char hint[32];
  snprintf(hint, sizeof(hint), state.musicPlaying ? "Playing" : "Paused");
  uiFontFaceMode = uiMusicStatusFont; uiFontAA = true;
  uiText(64, 124, hint, F_REG, state.musicPlaying ? theme.success : theme.warning, 1);
  uiFontFaceMode = savedFace;
  uiFontAA = savedAA;
  uiPageDots();
}

// ----------------------------------------------------------------------------
// Lyrics
// ----------------------------------------------------------------------------
static char  lyKey[128] = "";
static char  lyLines[4][40];
static int   lyN = 0;
static unsigned long lyChangeMs = 0;

void drawLyricsPage() {
  uint16_t accent = uiCoverAccent ? uiCoverAccent : theme.accent;
  if (hasLyricsBg && lyricsBg && uiBgBlurred) {
    memcpy(uiFb(), lyricsBg, UI_W * UI_H * sizeof(uint16_t));
  } else {
    uiBackground(accent, 46);
  }
  uiTopBar("Lyrics");

  if (!state.lyricsAvailable) {
    uiCard(38, 34, 52, 52, 12, uiCardCol(), theme.text, 40);
    uiText(64, 70, "...", F_BOLD, theme.secondary, 1);
    if (state.musicTitle[0] == '\0') {
      uiText(64, 106, "Nothing playing", F_BOLD, theme.text, 1);
      uiText(64, 120, "Open YouTube Music", F_REG, theme.secondary, 1);
    } else {
      uiText(64, 104, "No lyrics found", F_BOLD, theme.text, 1);
      uiTextFit(64, 118, state.musicTitle, F_REG, accent, 112, 1);
    }
    uiPageDots();
    return;
  }

  // Lyrics are the one place where content length is unbounded, so wrap at the
  // panel width using the active lyric face and allow four lines.
  const int LY_MAXW = 118;
  if (strcmp(lyKey, state.lyricCur) != 0) {
    strncpy(lyKey, state.lyricCur, sizeof(lyKey) - 1);
    lyKey[sizeof(lyKey) - 1] = 0;
    uiFontFaceMode = uiMusicUpcomingLyricFont; uiFontAA = uiMusicUpcomingLyricAA;
    lyN = uiWrap(state.lyricCur[0] ? state.lyricCur : "...", uiMusicUpcomingLyricFont, LY_MAXW, lyLines, 4);
    lyChangeMs = uiNowMs;
  }
  float t = uiEaseOut((uiNowMs - lyChangeMs) / 380.0f);
  int slide = (int)((1.0f - t) * 8.0f);

  uiPill(8, 22, 14, state.lyricsSynced ? "SYNCED" : "UNSYNCED", F_REG,
         state.lyricsSynced ? theme.success : theme.warning,
         uiLerp(theme.bg, state.lyricsSynced ? theme.success : theme.warning, 42), 6);
  if (state.lyricTotal > 0 && state.lyricIndex >= 0) {
    char p[16]; snprintf(p, sizeof(p), "%d/%d", state.lyricIndex + 1, state.lyricTotal);
    uiText(120, 33, p, uiMusicUpcomingLyricFont, theme.secondary, 2);
  }

  uiFontFaceMode = uiMusicUpcomingLyricFont; uiFontAA = uiMusicUpcomingLyricAA;
  uiTextFit(64, 51 + slide / 4, state.lyricPrev, uiMusicUpcomingLyricFont, uiFade(theme.text, 0.45f), LY_MAXW, 1);

  const int step = 9;
  int block = lyN * step, first = 80 - block / 2 + 7 + slide;
  uint16_t ac = uiFade(accent, 0.30f + 0.70f * t);
  for (int i = 0; i < lyN; i++)
    if (lyLines[i][0])
      uiTextFit(64, first + i * step, lyLines[i], uiMusicActiveLyricFont, ac, LY_MAXW, 1);

  uiFontFaceMode = uiMusicUpcomingLyricFont; uiFontAA = uiMusicUpcomingLyricAA;
  uiTextFit(64, 112 + slide / 3, state.lyricNext, uiMusicUpcomingLyricFont, uiFade(theme.text, 0.45f * t + 0.12f), LY_MAXW, 1);
  uiPageDots();
}

// ----------------------------------------------------------------------------
// PC monitor - three concentric rings
// ----------------------------------------------------------------------------
static float dCpu = 0, dMem = 0, dGpu = 0;

void drawPcPage() {
  uiBackground(theme.accent);
  uiTopBar("PC Monitor");
  uiSmooth(dCpu, state.cpu < 0 ? 0 : state.cpu, 5.0f);
  uiSmooth(dMem, state.mem < 0 ? 0 : state.mem, 5.0f);
  uiSmooth(dGpu, state.gpu < 0 ? 0 : state.gpu, 5.0f);

  const float cx = 64, cy = 72, th = 5;
  const float rr[3] = {44, 34, 24};
  const float vals[3] = {dCpu, dMem, dGpu};
  const float raw[3] = {state.cpu, state.mem, state.gpu};
  uint16_t cols[3];
  for (int i = 0; i < 3; i++) {
    cols[i] = uiLoadColor(raw[i] < 0 ? -1 : vals[i]);
    uiArc(cx, cy, rr[i], th, 1.0f, uiTrackCol());
    uiArc(cx, cy, rr[i], th, vals[i] / 100.0f, cols[i]);
  }

  // centre readout cycles CPU -> RAM -> GPU
  unsigned long period = 3200;
  int idx = (uiNowMs / period) % 3;
  float ph = (uiNowMs % period) / (float)period;
  float fade = uiClamp01(ph / 0.1f) * uiClamp01((1.0f - ph) / 0.1f);
  const char* names[3] = {"CPU", "RAM", "GPU"};
  uiText(cx, 66, names[idx], F_REG, uiFade(theme.secondary, fade), 1);
  char v[12];
  if (raw[idx] < 0) snprintf(v, sizeof(v), "n/a"); else snprintf(v, sizeof(v), "%d%%", (int)(vals[idx] + 0.5f));
  uiText(cx, 82, v, F_BIG, uiFade(cols[idx], fade), 1);
  char sub[16] = "";
  if (idx == 0) { float tt = state.cpuTemp >= 0 ? state.cpuTemp : state.thermalZone; if (tt >= 0) snprintf(sub, sizeof(sub), "%dC", (int)tt); }
  if (idx == 1 && state.gpuVramMb > 0) snprintf(sub, sizeof(sub), "%.0fG", state.gpuVramMb / 1024.0f);
  if (idx == 2 && state.gpuTemp >= 0) snprintf(sub, sizeof(sub), "%dC", (int)state.gpuTemp);
  if (sub[0]) uiText(cx, 94, sub, F_REG, uiFade(theme.text, fade * 0.8f), 1);

  const int xs[3] = {24, 64, 104};
  for (int i = 0; i < 3; i++) {
    char t[10]; if (raw[i] < 0) snprintf(t, sizeof(t), "--"); else snprintf(t, sizeof(t), "%d%%", (int)(vals[i] + 0.5f));
    uiText(xs[i], 132, t, F_BIG, cols[i], 1);
    uiText(xs[i], 144, names[i], F_REG, i == idx ? theme.text : theme.secondary, 1);
  }
  uiPageDots();
}

// ----------------------------------------------------------------------------
// Environment
// ----------------------------------------------------------------------------
static float dTemp = 0, dHum = 0, dPress = 1000;
static float micHist[20];
static unsigned long micHistMs = 0;

void drawEnvPage() {
  uiBackground(theme.accent);
  uiTopBar("Environment");
  bool haveT = !isnan(sensors.temperature), haveH = !isnan(sensors.humidity), haveP = !isnan(sensors.pressure);
  if (haveT) uiSmooth(dTemp, sensors.temperature, 6.0f);
  if (haveH) uiSmooth(dHum, sensors.humidity, 6.0f);
  if (haveP) uiSmooth(dPress, sensors.pressure, 6.0f);

  // temperature hero card
  uiCard(8, 22, 112, 40, 8, uiCardCol(), theme.text, 40, 255, uiLerp(uiCardCol(), theme.accent, 40), true);
  uiText(14, 33, "TEMPERATURE", F_REG, theme.secondary);
  char tb[12];
  if (haveT) snprintf(tb, sizeof(tb), "%.1f", dTemp); else snprintf(tb, sizeof(tb), "--.-");
  uiText(14, 55, tb, F_HUGE, theme.text);
  uiText(14 + uiW(tb, F_HUGE) + 4, 55, "C", F_BOLD, theme.accent);

  // humidity ring card
  uiPanel(8, 66, 54, 38, 8);
  uiArc(33, 84, 13, 4.0f, 1.0f, uiTrackCol());
  uiArc(33, 84, 13, 4.0f, dHum / 100.0f, theme.success);
  char hb[8]; if (haveH) snprintf(hb, sizeof(hb), "%d", (int)(dHum + 0.5f)); else snprintf(hb, sizeof(hb), "--");
  uiText(33, 87, hb, F_BIG, theme.text, 1);

  // pressure card
  uiPanel(66, 66, 54, 38, 8);
  char pb[10]; if (haveP) snprintf(pb, sizeof(pb), "%d", (int)(dPress + 0.5f)); else snprintf(pb, sizeof(pb), "--");
  uiText(93, 88, pb, F_BIG, theme.text, 1);
  uiText(93, 99, "hPa", F_REG, theme.secondary, 1);

  // microphone waveform card
  if (uiNowMs - micHistMs > 70) {
    micHistMs = uiNowMs;
    for (int i = 0; i < 19; i++) micHist[i] = micHist[i + 1];
    micHist[19] = sensors.micOk ? (float)sensors.micLevel : 0;
  }
  uiPanel(8, 108, 112, 24, 8);
  for (int i = 0; i < 20; i++) {
    float h = 2.0f + (micHist[i] / 100.0f) * 14.0f;
    uint16_t c = uiLerp(theme.accent, theme.warning, (uint8_t)(uiClamp01(micHist[i] / 100.0f) * 255));
    uiCard(14 + i * 5, 120 - h / 2, 3, h, 1.5f, sensors.micOk ? c : uiTrackCol(), c, 0);
  }

  char bl[32]; int bp = batteryPercent();
  if (bp == -2) snprintf(bl, sizeof(bl), "USB power");
  else if (bp == -1) snprintf(bl, sizeof(bl), "No battery");
  else snprintf(bl, sizeof(bl), "%.1fV  %d%%", sensors.batteryVoltage, bp);
  uiText(64, 140, bl, F_REG, theme.secondary, 1);
  uiPageDots();
}

// ----------------------------------------------------------------------------
// Notifications
// ----------------------------------------------------------------------------
static char uiLastNote0[48] = "";
static int  uiLastNoteCount = -1;
static unsigned long uiNoteMs = 0;

void drawNotificationsPage() {
  uiBackground(theme.warning, 28);
  uiTopBar("Notifications");

  if (noteCount != uiLastNoteCount || strcmp(uiLastNote0, noteCount ? notes[0].title : "") != 0) {
    uiLastNoteCount = noteCount;
    strncpy(uiLastNote0, noteCount ? notes[0].title : "", sizeof(uiLastNote0) - 1);
    uiNoteMs = uiNowMs;
  }

  if (noteCount == 0) {
    uiArc(64, 66, 22, 4, 1.0f, uiLerp(theme.bg, theme.success, 90));
    float k = uiEaseOut((uiNowMs % 4000) / 700.0f);
    sprite.drawLine(55, 67, 61, 73, theme.success);
    sprite.drawLine(55, 68, 61, 74, theme.success);
    sprite.drawLine(61, 73, 73, 59, theme.success);
    sprite.drawLine(61, 74, 73, 60, theme.success);
    uiAnnulus(64, 66, 22 + k * 8, 22 + k * 8 - 1.0f, theme.success, (uint8_t)((1 - k) * 110));
    uiText(64, 106, "All clear", F_BOLD, theme.text, 1);
    uiText(64, 120, "Alerts will show up here", F_REG, theme.secondary, 1);
    uiPageDots();
    return;
  }

  int shown = noteCount < 3 ? noteCount : 3;
  for (int i = 0; i < shown; i++) {
    float t = uiEaseOut(((uiNowMs - uiNoteMs) / 1000.0f - i * 0.09f) / 0.38f);
    int ox = (int)((1.0f - t) * 130.0f);
    int y = 21 + i * 36;
    const Note& n = notes[i];
    uint16_t pc = n.priority >= 3 ? theme.danger : (n.priority == 2 ? theme.warning : theme.accent);
    uiCard(8 + ox, y, 112, 32, 8, uiCardCol(), theme.text, 40);
    uiCard(8 + ox, y + 7, 3, 18, 1.5f, n.read ? uiTrackCol() : pc, pc, 0);
    if (!n.read) {
      float g = 0.5f + 0.5f * sinf(uiNowMs / 300.0f);
      uiDisc(110 + ox, y + 9, 4.0f + g, pc, 70);
      uiDisc(110 + ox, y + 9, 2.4f, pc);
    }
    uiTextFit(17 + ox, y + 13, n.title, F_BOLD, n.read ? theme.secondary : theme.text, 86);
    uiTextFit(17 + ox, y + 26, n.message, F_REG, theme.secondary, 96);
  }
  char f[32];
  if (noteCount > shown) snprintf(f, sizeof(f), "+%d more  SELECT: read", noteCount - shown);
  else snprintf(f, sizeof(f), "SELECT: mark as read");
  uiText(64, 140, f, F_REG, theme.secondary, 1);
  uiPageDots();
}

// ----------------------------------------------------------------------------
// Pomodoro
// ----------------------------------------------------------------------------
static float uiPomoF = 1.0f;
static int   uiPomoTotal = POMODORO_WORK_SECONDS;
static bool  uiPomoBreak = false;

void drawPomodoroPage() {
  uiBackground(pomodoro.isBreak ? theme.success : theme.warning, 40);
  uiTopBar("Pomodoro");

  if (pomodoro.isBreak != uiPomoBreak) { uiPomoBreak = pomodoro.isBreak; uiPomoTotal = pomodoro.remaining; }
  if (pomodoro.remaining > uiPomoTotal) uiPomoTotal = pomodoro.remaining;
  if (uiPomoTotal < 1) uiPomoTotal = 1;
  float target = uiClamp01((float)pomodoro.remaining / uiPomoTotal);
  uiSmooth(uiPomoF, target, 5.0f);

  uint16_t col = pomodoro.isBreak ? theme.success : theme.warning;
  if (!pomodoro.running) col = uiLerp(theme.secondary, col, 110);
  const float cx = 64, cy = 70, r = 39, th = 7;
  if (pomodoro.running) {
    float g = 0.5f + 0.5f * sinf(uiNowMs / 420.0f);
    uiAnnulus(cx, cy, r + th / 2 + 3 + g * 2, r - th / 2 - 3 - g * 2, col, (uint8_t)(10 + 14 * g));
  }
  uiArc(cx, cy, r, th, 1.0f, uiTrackCol());
  uiArc(cx, cy, r, th, uiPomoF, col);

  uiText(cx, 57, pomodoro.isBreak ? "BREAK" : "FOCUS", F_REG, theme.secondary, 1);
  char tb[8]; snprintf(tb, sizeof(tb), "%02d:%02d", pomodoro.remaining / 60, pomodoro.remaining % 60);
  uiText(cx, 80, tb, F_HUGE, pomodoro.running ? theme.text : uiLerp(theme.bg, theme.text, 190), 1);
  int done = pomodoro.session % 4;
  for (int i = 0; i < 4; i++)
    uiDisc(cx - 13.5f + i * 9, 92, 2.2f, i < done ? col : uiTrackCol());

  const char* st = pomodoro.running ? "RUNNING" : "PAUSED";
  uint16_t sc = pomodoro.running ? theme.success : theme.warning;
  int pw = uiW(st, F_REG) + 18;
  uiPill(64 - pw / 2, 102, 15, st, F_REG, sc, uiLerp(theme.bg, sc, 48), 9);
  uiText(64, 132, pomodoro.running ? "SELECT: pause" : "SELECT: start", F_REG, theme.secondary, 1);
  uiPageDots();
}

// ----------------------------------------------------------------------------
// Inspection mode
// ----------------------------------------------------------------------------
static float scopeH[3][60];
static float uiInspF = 0;

void drawInspectionPage() {
  uiBackground(theme.accent);
  uiTopBar("Inspection");

  for (int a = 0; a < 3; a++)
    for (int i = 0; i < 59; i++) scopeH[a][i] = scopeH[a][i + 1];
  scopeH[0][59] = sensors.accelX;
  scopeH[1][59] = sensors.accelY;
  scopeH[2][59] = sensors.accelZ - 9.81f;

  if (inspectResultReady) {
    bool normal = inspectResultClass[0] == 'N';
    uint16_t c = normal ? theme.success : theme.danger;
    uiPill(8, 22, 16, normal ? "HEALTHY" : "FAULT", F_REG, c, uiLerp(theme.bg, c, 48));
    char cls[28]; uiClean(cls, sizeof(cls), inspectResultClass);
    uiTextFit(8, 52, cls, F_BIG, theme.text, 112);
    uiPanel(8, 60, 112, 56, 10);
    uiSmooth(uiInspF, inspectResultConf, 6.0f);
    uiArc(34, 88, 18, 5, 1.0f, uiTrackCol());
    uiArc(34, 88, 18, 5, uiInspF, c);
    char pb[8]; snprintf(pb, sizeof(pb), "%d%%", (int)(uiInspF * 100 + 0.5f));
    uiText(34, 91, pb, F_BIG, theme.text, 1);
    uiText(90, 80, "WORST AXIS", F_REG, theme.secondary, 1);
    uiText(90, 103, inspectResultAxis, F_HUGE, c, 1);
    uiText(64, 130, "SELECT: new capture", F_REG, theme.secondary, 1);
    return;
  }

  if (inspectCapturing) {
    float target = (float)inspectCount / INSPECT_SAMPLES;
    uiSmooth(uiInspF, target, 10.0f);
    uiArc(64, 70, 38, 7, 1.0f, uiTrackCol());
    uiArc(64, 70, 38, 7, uiInspF, theme.warning);
    char nb[16]; snprintf(nb, sizeof(nb), "%d", inspectCount);
    uiText(64, 78, nb, F_HUGE, theme.text, 1);
    uiText(64, 92, "samples", F_REG, theme.secondary, 1);
    uiText(64, 124, "Capturing...", F_BOLD, theme.warning, 1);
    return;
  }

  uiInspF = 0;
  uiPanel(8, 21, 112, 72, 8);
  sprite.drawFastHLine(14, 57, 100, uiLerp(uiCardCol(), theme.text, 50));
  uint16_t sc[3] = {theme.accent, theme.success, theme.warning};
  for (int a = 0; a < 3; a++) {
    for (int i = 0; i < 59; i++) {
      float y0 = uiClamp(57 - scopeH[a][i] * 2.6f, 25, 89);
      float y1 = uiClamp(57 - scopeH[a][i + 1] * 2.6f, 25, 89);
      sprite.drawLine(14 + i * 100 / 59, (int)y0, 14 + (i + 1) * 100 / 59, (int)y1, sc[a]);
    }
  }
  const char* ax[3] = {"X", "Y", "Z"};
  for (int a = 0; a < 3; a++) {
    uiDisc(18 + a * 22, 85, 2.0f, sc[a]);
    uiText(23 + a * 22, 88, ax[a], F_REG, theme.secondary);
  }

  uiChip(8, 98, 54, sensors.adxlOk ? theme.success : theme.danger, "ADXL");
  uiChip(66, 98, 54, sensors.bmeOk ? theme.success : theme.danger, "BME");
  float p = 0.5f + 0.5f * sinf(uiNowMs / 380.0f);
  uiDisc(22, 126, 2.5f + p, theme.accent, 70);
  uiDisc(22, 126, 2.5f, theme.accent);
  uiText(31, 129, "SELECT: start capture", F_REG, theme.text);
  uiText(31, 141, "MODE: back to desk", F_REG, theme.secondary);
}

// ----------------------------------------------------------------------------
// Compatibility shims for old forward declarations
// ----------------------------------------------------------------------------
void drawHeader(const char* title) { uiTopBar(title); }
void drawBar(int x, int y, int w, int h, float percent, uint16_t color) {
  uiCard(x, y, w, h, h / 2.0f, uiTrackCol(), uiTrackCol(), 0);
  if (percent > 0) uiCard(x, y, fmaxf((float)h, w * uiClamp01(percent / 100.0f)), h, h / 2.0f, color, color, 0);
}
void drawBattery(int x, int y) { uiBatteryIcon(x, y); }

// ----------------------------------------------------------------------------
// Backlight + frame driver
// ----------------------------------------------------------------------------
void updateBacklight(unsigned long now) {
  int target = 220;
  if (wakeActive(now)) target = 255;
  else if (state.backendOnline && strcmp(state.sleepStage, "deep_sleep") == 0) target = 0;
  else if (state.backendOnline && strcmp(state.sleepStage, "sleeping") == 0) target = 18;
  else if (state.backendOnline && strcmp(state.sleepStage, "sleepy") == 0) target = 90;
  else if (!state.backendOnline) target = 150;

  // Fade, but only touch the PWM when it actually moves enough to matter
  // (avoids visible shimmer when the target jitters between states).
  static float cur = -1;
  if (cur < 0) cur = (float)target;
  cur += (target - cur) * 0.12f;
  int out = (int)(cur + 0.5f);
  if (abs(out - lastBacklight) >= 3) { analogWrite(PIN_TFT_BL, out); lastBacklight = out; }
}

// Framebuffers live in internal SRAM: they are scanned every frame and PSRAM
// latency shows up directly as stutter.
static inline uint16_t* uiAllocFrame() {
  uint32_t bytes = UI_W * UI_H * sizeof(uint16_t);
  uint16_t* p = (uint16_t*)heap_caps_malloc(bytes, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  return p ? p : (uint16_t*)malloc(bytes);
}

static uint16_t* uiLastPush = nullptr;   // last frame actually sent to the panel
static bool      uiPushValid = false;

static inline bool uiRowDiff(const uint16_t* a, const uint16_t* b) {
  const uint32_t* pa = (const uint32_t*)a;
  const uint32_t* pb = (const uint32_t*)b;
  for (int i = 0; i < UI_W / 2; i++) if (pa[i] != pb[i]) return true;
  return false;
}

// Push only the rows that changed. A static UI costs well under a millisecond
// of SPI instead of a fixed 16.6 ms. Transitions always push a full frame so
// the sliding content can never tear.
static void uiPush(const uint16_t* buf) {
  if (!uiLastPush) uiLastPush = uiAllocFrame();
  if (!uiLastPush || !uiPushValid || uiTransActive) {
    tft.drawRGBBitmap(0, 0, (uint16_t*)buf, UI_W, UI_H);
    if (uiLastPush) { memcpy(uiLastPush, buf, UI_W * UI_H * sizeof(uint16_t)); uiPushValid = true; }
    return;
  }
  int runStart = -1, runEnd = -1;
  for (int y = 0; y < UI_H; y++) {
    bool changed = uiRowDiff(buf + y * UI_W, uiLastPush + y * UI_W);
    if (changed) {
      if (runStart < 0) runStart = y;
      runEnd = y;
    } else if (runStart >= 0 && (y - runEnd) > 2) {
      int h = runEnd - runStart + 1;
      tft.drawRGBBitmap(0, runStart, (uint16_t*)(buf + runStart * UI_W), UI_W, h);
      memcpy(uiLastPush + runStart * UI_W, buf + runStart * UI_W, UI_W * h * sizeof(uint16_t));
      runStart = -1;
    }
  }
  if (runStart >= 0) {
    int h = runEnd - runStart + 1;
    tft.drawRGBBitmap(0, runStart, (uint16_t*)(buf + runStart * UI_W), UI_W, h);
    memcpy(uiLastPush + runStart * UI_W, buf + runStart * UI_W, UI_W * h * sizeof(uint16_t));
  }
}

static void uiAllocTransitionBuffers() {
  if (uiPrevBuf || uiCompBuf) return;
  // Only used during the 220ms slide, so PSRAM is fine here and keeps internal
  // SRAM free for the buffers that are scanned every frame.
  size_t sz = UI_W * UI_H * sizeof(uint16_t);
  uiPrevBuf = (uint16_t*)(psramFound() ? ps_malloc(sz) : malloc(sz));
  uiCompBuf = (uint16_t*)(psramFound() ? ps_malloc(sz) : malloc(sz));
  if (!uiPrevBuf || !uiCompBuf) {
    if (uiPrevBuf) free(uiPrevBuf);
    if (uiCompBuf) free(uiCompBuf);
    uiPrevBuf = uiCompBuf = nullptr;
  }
}

void drawFontTestPage();
static void uiRenderPage() {
  if (mode == MODE_INSPECTION) { drawInspectionPage(); return; }
  switch (page) {
    case PAGE_MUSIC: drawMusicPage(); break;
    case PAGE_LYRICS: drawLyricsPage(); break;
    case PAGE_PC: drawPcPage(); break;
    case PAGE_ENV: drawEnvPage(); break;
    case PAGE_NOTIFICATIONS: drawNotificationsPage(); break;
    case PAGE_POMODORO: drawPomodoroPage(); break;
    case PAGE_FONT_TEST: drawFontTestPage(); break;
    case PAGE_HOME:
    default: drawHome(); break;
  }
}

static const uint16_t* uiFrame(unsigned long now) {
  uiNowMs = now;
  uiDt = uiLastFrameMs ? uiClamp((now - uiLastFrameMs) / 1000.0f, 0.001f, 0.1f) : 0.04f;
  uiLastFrameMs = now;
  uiAllocTransitionBuffers();

  int key = ((int)mode << 8) | (int)page;
  if (uiLastKey >= 0 && key != uiLastKey && uiPrevBuf) {
    memcpy(uiPrevBuf, uiFb(), UI_W * UI_H * sizeof(uint16_t));
    uiTransActive = true;
    uiTransStart = now;
    int d = ((int)page - (uiLastKey & 0xFF) + PAGE_COUNT) % PAGE_COUNT;
    uiTransDir = ((uiLastKey >> 8) != (int)mode || d <= PAGE_COUNT / 2) ? 1 : -1;
  }
  uiLastKey = key;

  uiRenderPage();

  if (uiTransActive && uiPrevBuf && uiCompBuf) {
    float t = (now - uiTransStart) / (float)UI_TRANSITION_MS;
    if (t >= 1.0f) { uiTransActive = false; return uiFb(); }
    int off = (int)(uiEaseOut(t) * UI_W);
    if (off < 0) off = 0;
    if (off > UI_W) off = UI_W;
    uint16_t* nf = uiFb();
    for (int y = 0; y < UI_H; y++) {
      uint16_t* d = uiCompBuf + y * UI_W;
      const uint16_t* a = uiPrevBuf + y * UI_W;
      const uint16_t* b = nf + y * UI_W;
      if (uiTransDir > 0) {
        memcpy(d, a + off, (UI_W - off) * 2);
        memcpy(d + (UI_W - off), b, off * 2);
      } else {
        memcpy(d, b + (UI_W - off), off * 2);
        memcpy(d + off, a, (UI_W - off) * 2);
      }
    }
    return uiCompBuf;
  }
  uiTransActive = false;
  return uiFb();
}

#if defined(HAS_U8G2_GFX)
void drawFontTestPage() {
  uiBackground(theme.bg, 8);
  uiTopBar("Font Test");

  u8g2gfx.setForegroundColor(theme.text);
  u8g2gfx.setBackgroundColor(theme.bg);
  u8g2gfx.setFontMode(1);

  const uint8_t* fonts[6] = {
    u8g2_font_6x12_tf,
    u8g2_font_7x14_tf,
    u8g2_font_helvR08_tf,
    u8g2_font_helvR10_tf,
    u8g2_font_helvB10_tf,
    u8g2_font_profont10_tf
  };
  const char* names[6] = {
    "u8g2_font_6x12_tf",
    "u8g2_font_7x14_tf",
    "u8g2_font_helvR08_tf",
    "u8g2_font_helvR10_tf",
    "u8g2_font_helvB10_tf",
    "u8g2_font_profont10_tf"
  };

  int y = 24;
  for (int i = 0; i < 6; i++) {
    u8g2gfx.setFont(fonts[i]);
    u8g2gfx.drawStr(4, y, names[i]);
    y += 12;
    u8g2gfx.drawStr(4, y, "The quick brown fox 0123");
    y += 14;
    if (y > UI_H - 10) break;
  }

  uiPageDots();
}
#else
void drawFontTestPage() {
  uiBackground(theme.bg, 8);
  uiTopBar("Font Test");
  uiText(8, 40, "U8g2_for_Adafruit_GFX not available", F_REG, theme.danger, 0);
  uiPageDots();
}
#endif

void drawTft(unsigned long now) {
  updateBacklight(now);
  if (state.backendOnline && strcmp(state.sleepStage, "deep_sleep") == 0 && !wakeActive(now) && mode != MODE_INSPECTION) {
    return;  // screen is dark in deep sleep; skip the work
  }
  tftFullRedraw = false;
#if UI_PROFILE
  unsigned long tR0 = micros();
  const uint16_t* fbuf = uiFrame(now);
  unsigned long tR1 = micros();
  uiPush(fbuf);
  unsigned long tR2 = micros();
  static uint32_t accR = 0, accP = 0, maxR = 0, maxP = 0;
  static uint16_t n = 0;
  uint32_t r = tR1 - tR0, p = tR2 - tR1;
  accR += r; accP += p;
  if (r > maxR) maxR = r;
  if (p > maxP) maxP = p;
  if (++n >= 30) {
    Serial.printf("#UI page=%d render=%.1fms push=%.1fms maxr=%.1f maxp=%.1f\n",
                  (int)page, accR / 30.0f / 1000.0f, accP / 30.0f / 1000.0f,
                  maxR / 1000.0f, maxP / 1000.0f);
    n = 0; accR = accP = maxR = maxP = 0;
  }
#else
  uiPush(uiFrame(now));
#endif
}

// ----------------------------------------------------------------------------
// Boot animation
// ----------------------------------------------------------------------------
void uiBoot() {
  unsigned long t0 = millis(), last = t0;
  while (true) {
    unsigned long now = millis();
    float t = (now - t0) / 1400.0f;
    if (t >= 1.0f) break;
    uiNowMs = now;
    uiDt = uiClamp((now - last) / 1000.0f, 0.001f, 0.1f);
    last = now;
    uiBackground(theme.accent, 70);
    float e = uiEaseOut(t * 1.3f);
    uiArc(64, 58, 24, 5, 1.0f, uiTrackCol());
    uiArc(64, 58, 24, 5, 0.08f + 0.9f * e, theme.accent, 255, t * 9.0f);
    uiDisc(64, 58, 3.5f + 1.2f * sinf(t * 14.0f), theme.text, (uint8_t)(255 * uiClamp01(t * 3)));
    float a1 = uiClamp01((t - 0.25f) / 0.3f), a2 = uiClamp01((t - 0.45f) / 0.3f);
    uiText(64, 104 + (int)((1 - a1) * 8), "DeskBuddy", F_BOLD, uiFade(theme.text, a1), 1);
    uiText(64, 122, "PC-aware desk companion", F_REG, uiFade(theme.secondary, a2), 1);
    uiText(64, 140, "v" FW_VERSION, F_REG, uiFade(theme.secondary, a2 * 0.7f), 1);
    uiPush(uiFb());
    delay(5);
  }
}
