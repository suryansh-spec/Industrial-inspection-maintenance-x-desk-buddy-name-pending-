// ============================================================================
// ui_modern.h - modern TFT UI for DeskBuddy (Adafruit GFX / GFXcanvas16)
// ============================================================================
// Drop-in replacement for the old "TFT dashboard" section of the sketch.
// Keep this file in the same folder as DeskBuddy_Companion.ino.
//
// What it adds
//   * Anti-aliased ring gauges, rounded cards, pills (software AA, RGB565)
//   * Smooth fonts (FreeSans family) instead of the 6x8 bitmap font
//   * Every frame is fully re-rendered into the sprite -> real animation
//   * Page slide transitions (old/new frames panned together)
//   * Count-up / lerped values, marquee titles, karaoke-style lyrics,
//     album-colour theming, blurred cover background, notification slide-in
//
// Tuning knobs: UI_FRAME_MS (frame period) and UI_TRANSITION_MS below.
// ============================================================================
#pragma once

#include <Fonts/FreeSans9pt7b.h>
#include <Fonts/FreeSansBold9pt7b.h>
#include <Fonts/FreeSansBold12pt7b.h>
#include <Fonts/FreeSansBold18pt7b.h>

#define UI_W 128
#define UI_H 160
#define UI_FRAME_MS 33          // ~30 fps
#define UI_TRANSITION_MS 260
#define UI_PI 3.14159265f
#define UI_HALF_PI 1.57079633f
#define UI_TWO_PI 6.28318531f
#define UI_COVER 72             // upscaled album art size on the music page
#define UI_MQ_W 112

#define F_REG  (&FreeSans9pt7b)
#define F_BOLD (&FreeSansBold9pt7b)
#define F_BIG  (&FreeSansBold12pt7b)
#define F_HUGE (&FreeSansBold18pt7b)

// ----------------------------------------------------------------------------
// Core state
// ----------------------------------------------------------------------------
static float         uiDt = 0.033f;     // seconds since previous frame
static unsigned long uiNowMs = 0;
static unsigned long uiLastFrameMs = 0;
static int           uiLastKey = -1;

static uint16_t* uiPrevBuf = nullptr;   // snapshot of outgoing page
static uint16_t* uiCompBuf = nullptr;   // composed transition frame
static bool          uiTransActive = false;
static unsigned long uiTransStart = 0;
static int           uiTransDir = 1;

static uint16_t* uiCoverBig = nullptr;  // 72x72 smoothed album art
static bool      uiCoverReady = false;
static uint16_t  uiCoverAccent = 0;     // dominant album colour (0 = none)
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
static inline uint16_t uiCardCol()   { return uiLerp(theme.bg, theme.text, 20); }
static inline uint16_t uiTrackCol()  { return uiLerp(theme.bg, theme.text, 46); }
static inline uint16_t uiFade(uint16_t c, float a) { return uiLerp(theme.bg, c, (uint8_t)(uiClamp01(a) * 255.0f)); }

// 0..100 -> green .. amber .. red
static uint16_t uiLoadColor(float v) {
  if (v < 0) return theme.secondary;
  if (v <= 45) return theme.success;
  if (v <= 75) return uiLerp(theme.success, theme.warning, (uint8_t)((v - 45) / 30.0f * 255));
  if (v <= 90) return uiLerp(theme.warning, theme.danger, (uint8_t)((v - 75) / 15.0f * 255));
  return theme.danger;
}

// alpha-blended pixel
static inline void uiPx(int x, int y, uint16_t c, uint8_t a) {
  if ((unsigned)x >= UI_W || (unsigned)y >= UI_H || a == 0) return;
  uint16_t* p = &uiFb()[y * UI_W + x];
  *p = (a == 255) ? c : uiLerp(*p, c, a);
}

// ----------------------------------------------------------------------------
// Anti-aliased shapes
// ----------------------------------------------------------------------------
// Disc (rIn <= 0) or annulus with soft edges.
static void uiAnnulus(float cx, float cy, float rOut, float rIn, uint16_t col, uint8_t alpha = 255) {
  int x0 = (int)floorf(cx - rOut - 1), x1 = (int)ceilf(cx + rOut + 1);
  int y0 = (int)floorf(cy - rOut - 1), y1 = (int)ceilf(cy + rOut + 1);
  float lo = (rIn > 0) ? (rIn - 1.0f) : -1.0f;
  float lo2 = lo > 0 ? lo * lo : -1.0f, hi2 = (rOut + 1.0f) * (rOut + 1.0f);
  for (int y = y0; y <= y1; y++) {
    for (int x = x0; x <= x1; x++) {
      float dx = x + 0.5f - cx, dy = y + 0.5f - cy, d2 = dx * dx + dy * dy;
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

// Progress arc with round caps. frac 0..1 sweeps clockwise from the top
// (rotated by `rot` radians). Round caps hide the hard angular edge.
static void uiArc(float cx, float cy, float rMid, float th, float frac, uint16_t col,
                  uint8_t alpha = 255, float rot = 0.0f) {
  if (frac <= 0.0f) return;
  frac = uiClamp01(frac);
  float rO = rMid + th * 0.5f, rI = rMid - th * 0.5f, cr = th * 0.5f;
  float sweep = frac * UI_TWO_PI;
  bool full = frac >= 0.999f;
  float a0 = -UI_HALF_PI + rot, a1 = a0 + sweep;
  float c0x = cx + rMid * cosf(a0), c0y = cy + rMid * sinf(a0);
  float c1x = cx + rMid * cosf(a1), c1y = cy + rMid * sinf(a1);
  int x0 = (int)floorf(cx - rO - 1), x1 = (int)ceilf(cx + rO + 1);
  int y0 = (int)floorf(cy - rO - 1), y1 = (int)ceilf(cy + rO + 1);
  float lo = rI - 1.0f; float lo2 = lo > 0 ? lo * lo : -1.0f, hi2 = (rO + 1.0f) * (rO + 1.0f);
  for (int y = y0; y <= y1; y++) {
    for (int x = x0; x <= x1; x++) {
      float px = x + 0.5f, py = y + 0.5f;
      float dx = px - cx, dy = py - cy, d2 = dx * dx + dy * dy;
      if (d2 > hi2 || d2 < lo2) continue;
      float d = sqrtf(d2);
      float ring = uiClamp01(fminf(rO - d + 0.5f, d - rI + 0.5f));
      float cov = 0;
      if (full) cov = ring;
      else {
        float ang = atan2f(dy, dx) + UI_HALF_PI - rot;
        while (ang < 0) ang += UI_TWO_PI;
        while (ang >= UI_TWO_PI) ang -= UI_TWO_PI;
        if (ang <= sweep) cov = ring;
        float e0 = uiClamp01(cr - sqrtf((px - c0x) * (px - c0x) + (py - c0y) * (py - c0y)) + 0.5f);
        float e1 = uiClamp01(cr - sqrtf((px - c1x) * (px - c1x) + (py - c1y) * (py - c1y)) + 0.5f);
        if (e0 > cov) cov = e0;
        if (e1 > cov) cov = e1;
      }
      if (cov > 0) uiPx(x, y, col, (uint8_t)(cov * alpha));
    }
  }
}

// Rounded rectangle with optional vertical gradient and 1px border (SDF based).
static void uiCard(float x, float y, float w, float h, float r, uint16_t fill,
                   uint16_t border, uint8_t borderA = 0, uint8_t fillA = 255,
                   uint16_t fill2 = 0, bool grad = false) {
  float hx = w * 0.5f, hy = h * 0.5f, cx = x + hx, cy = y + hy;
  if (r > hx) r = hx;
  if (r > hy) r = hy;
  int x0 = (int)floorf(x) - 1, y0 = (int)floorf(y) - 1;
  int x1 = (int)ceilf(x + w) + 1, y1 = (int)ceilf(y + h) + 1;
  for (int py = y0; py <= y1; py++) {
    if (py < 0 || py >= UI_H) continue;
    uint16_t rowc = grad ? uiLerp(fill, fill2, (uint8_t)(uiClamp01((py - y) / h) * 255)) : fill;
    float qy = fabsf(py + 0.5f - cy) - (hy - r);
    for (int px = x0; px <= x1; px++) {
      if (px < 0 || px >= UI_W) continue;
      float qx = fabsf(px + 0.5f - cx) - (hx - r);
      float d;
      if (qx > 0 || qy > 0) {
        float ox = qx > 0 ? qx : 0, oy = qy > 0 ? qy : 0;
        d = sqrtf(ox * ox + oy * oy) - r + fminf(fmaxf(qx, qy), 0.0f);
      } else d = fmaxf(qx, qy) - r;
      float cov = uiClamp01(0.5f - d);
      if (cov <= 0) continue;
      uint16_t c = rowc;
      if (borderA && d > -1.0f) c = uiLerp(c, border, (uint8_t)(uiClamp01(d + 1.0f) * borderA));
      uiPx(px, py, c, (uint8_t)(cov * fillA));
    }
  }
}
static inline void uiPanel(float x, float y, float w, float h, float r = 8) {
  uiCard(x, y, w, h, r, uiCardCol(), theme.text, 34);
}

// ----------------------------------------------------------------------------
// Text
// ----------------------------------------------------------------------------
static void uiClean(char* dst, size_t sz, const char* src) {
  size_t n = 0; bool skipped = false;
  if (!src) { dst[0] = 0; return; }
  for (; *src && n + 1 < sz; src++) {
    uint8_t c = (uint8_t)*src;
    if (c >= 0x20 && c < 0x7F) { dst[n++] = (char)c; skipped = false; }
    else if (c >= 0x80 && !skipped && n + 1 < sz) { if ((c & 0xC0) != 0x80) { dst[n++] = '?'; skipped = true; } }
  }
  dst[n] = 0;
}
static int uiW(const char* s, const GFXfont* f) {
  int16_t x1, y1; uint16_t w, h;
  sprite.setFont(f); sprite.setTextSize(1);
  sprite.getTextBounds(s, 0, 0, &x1, &y1, &w, &h);
  return (int)w;
}
// align: 0 left, 1 centre, 2 right. y is the text baseline.
static void uiText(int x, int y, const char* s, const GFXfont* f, uint16_t col, int align = 0) {
  int16_t x1, y1; uint16_t w, h;
  sprite.setFont(f); sprite.setTextSize(1); sprite.setTextColor(col);
  sprite.getTextBounds(s, 0, 0, &x1, &y1, &w, &h);
  int px = (align == 0) ? x - x1 : (align == 1 ? x - (int)w / 2 - x1 : x - (int)w - x1);
  sprite.setCursor(px, y);
  sprite.print(s);
}
static void uiFit(char* out, size_t sz, const char* s, const GFXfont* f, int maxW) {
  uiClean(out, sz, s);
  if (uiW(out, f) <= maxW) return;
  int n = strlen(out);
  while (n > 1) {
    out[--n] = 0;
    char t[100]; snprintf(t, sizeof(t), "%s..", out);
    if (uiW(t, f) <= maxW) { strncpy(out, t, sz - 1); out[sz - 1] = 0; return; }
  }
}
static void uiTextFit(int x, int y, const char* s, const GFXfont* f, uint16_t col, int maxW, int align = 0) {
  char t[100]; uiFit(t, sizeof(t), s, f, maxW); uiText(x, y, t, f, col, align);
}

// Scrolls long text inside a clipped window; short text is centred / left aligned.
static GFXcanvas16* uiMq = nullptr;
static void uiMarquee(int x, int baseline, int w, const char* s, const GFXfont* f,
                      uint16_t col, uint16_t bg, bool center) {
  char t[100]; uiClean(t, sizeof(t), s);
  int tw = uiW(t, f);
  if (tw <= w) { uiText(center ? x + w / 2 : x, baseline, t, f, col, center ? 1 : 0); return; }
  if (!uiMq) uiMq = new GFXcanvas16(UI_MQ_W, 18);
  if (!uiMq || !uiMq->getBuffer() || w > UI_MQ_W) { uiTextFit(x, baseline, t, f, col, w); return; }
  uiMq->fillScreen(bg);
  uiMq->setFont(f); uiMq->setTextSize(1); uiMq->setTextColor(col);
  int loop = tw + 28;
  unsigned long period = (unsigned long)loop * 28 + 1400, ph = uiNowMs % period;
  int off = ph < 1400 ? 0 : (int)((ph - 1400) / 28);
  int16_t x1, y1; uint16_t bw, bh;
  uiMq->getTextBounds(t, 0, 0, &x1, &y1, &bw, &bh);
  for (int k = 0; k < 2; k++) { uiMq->setCursor(-x1 - off + k * loop, 13); uiMq->print(t); }
  uint16_t* b = uiMq->getBuffer();
  for (int row = 0; row < 18; row++) {
    uint16_t* r = b + row * UI_MQ_W;
    for (int i = 0; i < 7; i++) {
      uint8_t a = (uint8_t)((i + 1) * 255 / 8);
      r[i] = uiLerp(bg, r[i], a);
      r[w - 1 - i] = uiLerp(bg, r[w - 1 - i], a);
    }
    sprite.drawRGBBitmap(x, baseline - 13 + row, r, w, 1);
  }
}

// Word wrap by pixel width. Returns line count.
static int uiWrap(const char* s, const GFXfont* f, int maxW, char out[][40], int maxLines) {
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
        if (uiW(buf, f) <= maxW) lastFit = i; else break;
        if (t[i] == '\0') break;
      }
    }
    if (lastFit < 0) {
      int l = 0;
      while (pos + l < len && l < 38) {
        memcpy(buf, t + pos, l + 1); buf[l + 1] = 0;
        if (uiW(buf, f) > maxW) break; l++;
      }
      if (l < 1) l = 1;
      lastFit = pos + l;
    }
    int l = lastFit - pos; if (l > 39) l = 39;
    memcpy(out[n], t + pos, l); out[n][l] = 0; n++;
    pos = lastFit;
  }
  while (pos < len && t[pos] == ' ') pos++;
  if (pos < len && n > 0) {
    char tmp[44]; snprintf(tmp, sizeof(tmp), "%.37s..", out[n - 1]);
    uiFit(out[n - 1], 40, tmp, f, maxW);
  }
  return n;
}

static void uiFmtTime(int sec, char* buf, size_t sz) {
  if (sec < 0) sec = 0;
  snprintf(buf, sz, "%d:%02d", sec / 60, sec % 60);
}

// ----------------------------------------------------------------------------
// Small widgets
// ----------------------------------------------------------------------------
static void uiBackground(uint16_t glow, uint8_t amt = 34) {
  uint16_t* b = uiFb();
  for (int y = 0; y < UI_H; y++) {
    uint16_t c = theme.bg;
    if (y < 80) { float k = 1.0f - y / 80.0f; c = uiLerp(theme.bg, glow, (uint8_t)(amt * k * k)); }
    uint16_t* r = b + y * UI_W;
    for (int x = 0; x < UI_W; x++) r[x] = c;
  }
}

static void uiBatteryIcon(int x, int y) {
  int pct = batteryPercent();
  if (pct == -1) return;
  uiCard(x, y, 18, 9, 3, uiCardCol(), theme.text, 90);
  sprite.fillRect(x + 18, y + 3, 2, 3, uiLerp(theme.bg, theme.text, 90));
  if (pct == -2) {
    uiCard(x + 2, y + 2, 14, 5, 1.5f, theme.success, theme.success, 0);
  } else if (pct >= 0) {
    uint16_t c = pct < 20 ? theme.danger : (pct < 50 ? theme.warning : theme.success);
    int fw = (pct * 14) / 100; if (fw < 2 && pct > 0) fw = 2;
    if (fw > 0) uiCard(x + 2, y + 2, fw, 5, 1.5f, c, c, 0);
  }
}

static void uiTopBar(const char* title) {
  uiText(8, 15, title, F_BOLD, theme.text);
  uiBatteryIcon(92, 4);
  uint16_t lc = state.backendOnline ? theme.success : theme.danger;
  uiDisc(120, 8.5f, 3.0f, lc);
  if (state.backendOnline) {
    float ph = fmodf(uiNowMs / 1800.0f, 1.0f);
    uiAnnulus(120, 8.5f, 3.0f + ph * 5.5f, 3.0f + ph * 5.5f - 1.2f, lc, (uint8_t)((1.0f - ph) * 170));
  }
}

static float uiPageF = 0;
static void uiPageDots() {
  const int n = PAGE_COUNT, gap = 11, y = 154;
  uiSmooth(uiPageF, (float)page, 14.0f);
  int x0 = 64 - ((n - 1) * gap) / 2;
  for (int i = 0; i < n; i++) uiDisc(x0 + i * gap, y, 1.7f, theme.secondary, 110);
  uiCard(x0 + uiPageF * gap - 6, y - 2, 12, 4, 2, theme.accent, theme.accent, 0);
}

static int uiPill(int x, int y, int h, const char* s, const GFXfont* f, uint16_t fg, uint16_t bgc, int padX = 9) {
  int tw = uiW(s, f), w = tw + padX * 2;
  uiCard(x, y, w, h, h / 2.0f, bgc, fg, 0);
  uiText(x + padX, y + h - 5, s, f, fg);
  return w;
}

static void uiChip(int x, int y, int w, uint16_t dot, const char* s) {
  uiPanel(x, y, w, 18, 9);
  uiDisc(x + 10, y + 9, 2.6f, dot);
  uiText(x + 17, y + 14, s, F_REG, theme.text);
}

static void uiEq(int x, int baseY, int n, uint16_t col, bool playing) {
  for (int i = 0; i < n; i++) {
    float h = playing ? 3.0f + (0.5f + 0.5f * sinf(uiNowMs / 170.0f + i * 1.7f)) * 8.0f : 3.0f;
    uiCard(x + i * 5, baseY - h, 3, h, 1.5f, col, col, 0);
  }
}

static void uiNoteGlyph(float x, float y, uint16_t col) {
  uiDisc(x, y, 3.0f, col);
  sprite.fillRect((int)x + 2, (int)y - 11, 2, 11, col);
  sprite.fillRect((int)x + 2, (int)y - 11, 6, 3, col);
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

// Blur + darken the upscaled lyrics background once, so text stays readable.
void uiOnCoverBg() {
  if (!lyricsBg) return;
  static uint16_t* tmp = nullptr;
  size_t sz = TFT_W * TFT_H * sizeof(uint16_t);
  if (!tmp) tmp = (uint16_t*)(psramFound() ? ps_malloc(sz) : malloc(sz));
  if (!tmp) return;
  const int R = 6, N = 2 * R + 1;
  for (int pass = 0; pass < 2; pass++) {
    for (int y = 0; y < TFT_H; y++) {
      for (int x = 0; x < TFT_W; x++) {
        int sr = 0, sg = 0, sb = 0;
        for (int k = -R; k <= R; k++) {
          int xx = x, yy = y;
          if (pass == 0) { xx = x + k; if (xx < 0) xx = 0; if (xx > TFT_W - 1) xx = TFT_W - 1; }
          else           { yy = y + k; if (yy < 0) yy = 0; if (yy > TFT_H - 1) yy = TFT_H - 1; }
          int r, g, b; uiUnpack((pass == 0 ? lyricsBg : tmp)[yy * TFT_W + xx], r, g, b);
          sr += r; sg += g; sb += b;
        }
        uint16_t c = uiPack(sr / N, sg / N, sb / N);
        if (pass == 0) tmp[y * TFT_W + x] = c; else lyricsBg[y * TFT_W + x] = uiLerp(c, theme.bg, 172);
      }
    }
  }
  uiBgBlurred = true;
}

// ----------------------------------------------------------------------------
// Home
// ----------------------------------------------------------------------------
static void uiNowPlayingCard(int y) {
  uiPanel(8, y, 112, 17, 8);
  if (state.musicTitle[0]) {
    uiEq(17, y + 13, 3, state.musicPlaying ? theme.success : theme.secondary, state.musicPlaying);
  } else {
    uiNoteGlyph(21, y + 12, theme.secondary);
  }
  if (state.musicTitle[0])
    uiMarquee(36, y + 13, 80, state.musicTitle, F_REG, state.musicPlaying ? theme.text : theme.secondary, uiCardCol(), false);
  else
    uiText(36, y + 13, "No music", F_REG, theme.secondary);
}

void drawHome() {
  uiBackground(theme.accent);
  uiTopBar("DeskBuddy");

  // clock with a softly pulsing colon
  const char* clk = state.clockText[0] ? state.clockText : "--:--";
  char hh[8] = "--", mm[8] = "--";
  const char* colon = strchr(clk, ':');
  if (colon) { size_t n = colon - clk; if (n > 5) n = 5; memcpy(hh, clk, n); hh[n] = 0; strncpy(mm, colon + 1, 5); mm[5] = 0; }
  int wH = uiW(hh, F_HUGE), wC = uiW(":", F_HUGE);
  int x = 8;
  uiText(x, 52, hh, F_HUGE, theme.text);
  float pulse = 0.35f + 0.65f * (0.5f + 0.5f * sinf(uiNowMs / 320.0f));
  uiText(x + wH + 3, 50, ":", F_HUGE, uiFade(theme.accent, pulse));
  uiText(x + wH + wC + 8, 52, mm, F_HUGE, theme.text);

  if (state.unread > 0) {
    float pr = 1.0f + 0.12f * sinf(uiNowMs / 260.0f);
    uiDisc(112, 40, 9.5f * pr, theme.warning);
    char n[6]; snprintf(n, sizeof(n), "%d", state.unread > 9 ? 9 : state.unread);
    uiText(112, 45, n, F_BOLD, theme.bg, 1);
  }

  char dl[40]; snprintf(dl, sizeof(dl), "%s %s", state.dowText, state.dateText[0] ? state.dateText : "--");
  uiTextFit(8, 68, dl, F_REG, theme.secondary, 112);

  const char* act = activityLabel();
  if (act[0]) {
    int w = uiPill(8, 75, 18, act, F_BOLD, theme.warning, uiLerp(theme.bg, theme.warning, 46));
    (void)w;
  }
  uiTextFit(8, 107, state.appName[0] ? state.appName : "Waiting for PC...", F_REG, theme.text, 112);

  char t[16], h[16];
  if (isnan(sensors.temperature)) snprintf(t, sizeof(t), "--.-C"); else snprintf(t, sizeof(t), "%.1fC", sensors.temperature);
  if (isnan(sensors.humidity)) snprintf(h, sizeof(h), "--%%"); else snprintf(h, sizeof(h), "%.0f%%", sensors.humidity);
  uiChip(8, 112, 54, theme.accent, t);
  uiChip(66, 112, 54, theme.success, h);

  uiNowPlayingCard(134);
  uiPageDots();
}

// ----------------------------------------------------------------------------
// Music
// ----------------------------------------------------------------------------
static float uiPlayT = 1.0f, uiProg = 0.0f;
static char  uiLastTitle[64] = "";

void drawMusicPage() {
  uint16_t accent = (uiCoverAccent && state.musicTitle[0]) ? uiCoverAccent : theme.accent;
  uiBackground(accent, 52);
  uiTopBar("Music");

  if (state.musicTitle[0] == '\0') {
    uiCard(36, 40, 56, 56, 16, uiCardCol(), theme.text, 34);
    uiNoteGlyph(60, 78, theme.secondary);
    uiText(64, 122, "Nothing playing", F_BOLD, theme.text, 1);
    uiText(64, 140, "Open YouTube Music", F_REG, theme.secondary, 1);
    uiPageDots();
    return;
  }
  if (strcmp(uiLastTitle, state.musicTitle) != 0) { strncpy(uiLastTitle, state.musicTitle, sizeof(uiLastTitle) - 1); uiProg = -1; }

  uiSmooth(uiPlayT, state.musicPlaying ? 1.0f : 0.0f, 9.0f);
  const int cx = (UI_W - UI_COVER) / 2, cy = 21;

  // soft halo that breathes while playing
  float breathe = 0.5f + 0.5f * sinf(uiNowMs / 480.0f);
  for (int i = 4; i >= 1; i--)
    uiCard(cx - i * 3, cy - i * 3, UI_COVER + i * 6, UI_COVER + i * 6, 10 + i * 3, accent, accent, 0,
           (uint8_t)((7 + 7 * breathe * uiPlayT) * (5 - i) * (0.35f + 0.65f * uiPlayT)));

  float dim = (1.0f - uiPlayT) * 0.55f;
  if (uiCoverReady && uiCoverBig) {
    const float R = 10.0f;
    uint8_t dimA = (uint8_t)(dim * 255);
    for (int yy = 0; yy < UI_COVER; yy++) {
      for (int xx = 0; xx < UI_COVER; xx++) {
        float cov = 1.0f;
        int dx = xx < UI_COVER - 1 - xx ? xx : UI_COVER - 1 - xx;
        int dy = yy < UI_COVER - 1 - yy ? yy : UI_COVER - 1 - yy;
        if (dx < R && dy < R) {
          float ox = R - dx - 0.5f, oy = R - dy - 0.5f;
          cov = uiClamp01(R - sqrtf(ox * ox + oy * oy) + 0.5f);
          if (cov <= 0) continue;
        }
        uint16_t c = uiCoverBig[yy * UI_COVER + xx];
        if (dimA) c = uiLerp(c, theme.bg, dimA);
        uiPx(cx + xx, cy + yy, c, (uint8_t)(cov * 255));
      }
    }
  } else {
    uiCard(cx, cy, UI_COVER, UI_COVER, 10, uiLerp(theme.bg, accent, 70), accent, 60);
    uiNoteGlyph(cx + 34, cy + 46, accent);
  }
  // pause badge fades in over the cover
  if (uiPlayT < 0.98f) {
    uint8_t a = (uint8_t)((1.0f - uiPlayT) * 235);
    uiCard(cx + 25, cy + 22, 7, 28, 3, theme.text, theme.text, 0, a);
    uiCard(cx + 40, cy + 22, 7, 28, 3, theme.text, theme.text, 0, a);
  }

  uiMarquee(8, 110, 112, state.musicTitle, F_BOLD, theme.text, theme.bg, true);
  uiTextFit(64, 124, state.musicArtist[0] ? state.musicArtist : "Unknown artist", F_REG, theme.secondary, 112, 1);

  float target = state.musicDuration > 0 ? uiClamp01((float)state.musicProgress / state.musicDuration) : 0.0f;
  if (uiProg < 0) uiProg = target;
  uiSmooth(uiProg, target, 6.0f);
  uiCard(8, 131, 112, 4, 2, uiTrackCol(), uiTrackCol(), 0);
  if (uiProg > 0.002f) uiCard(8, 131, fmaxf(4.0f, 112 * uiProg), 4, 2, accent, accent, 0);
  uiDisc(8 + 112 * uiProg, 133, 4.2f, theme.text);

  char a[12], b[12]; uiFmtTime(state.musicProgress, a, sizeof(a)); uiFmtTime(state.musicDuration, b, sizeof(b));
  uiText(8, 148, a, F_REG, theme.secondary, 0);
  uiText(120, 148, b, F_REG, theme.secondary, 2);
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
    uiCard(36, 40, 56, 56, 16, uiCardCol(), theme.text, 34);
    uiText(64, 76, "...", F_HUGE, theme.secondary, 1);
    if (state.musicTitle[0] == '\0') {
      uiText(64, 122, "Nothing playing", F_BOLD, theme.text, 1);
      uiText(64, 140, "Open YouTube Music", F_REG, theme.secondary, 1);
    } else {
      uiText(64, 118, "No lyrics found", F_BOLD, theme.text, 1);
      uiTextFit(64, 135, state.musicTitle, F_REG, accent, 112, 1);
    }
    uiPageDots();
    return;
  }

  if (strcmp(lyKey, state.lyricCur) != 0) {
    strncpy(lyKey, state.lyricCur, sizeof(lyKey) - 1);
    lyN = uiWrap(state.lyricCur[0] ? state.lyricCur : "...", F_BOLD, 108, lyLines, 4);
    lyChangeMs = uiNowMs;
  }
  float t = uiEaseOut((uiNowMs - lyChangeMs) / 380.0f);
  int slide = (int)((1.0f - t) * 18.0f);

  // sync badge + position
  uiPill(8, 21, 16, state.lyricsSynced ? "SYNCED" : "UNSYNCED", F_REG,
         state.lyricsSynced ? theme.success : theme.warning,
         uiLerp(theme.bg, state.lyricsSynced ? theme.success : theme.warning, 40), 7);
  if (state.lyricTotal > 0 && state.lyricIndex >= 0) {
    char p[16]; snprintf(p, sizeof(p), "%d/%d", state.lyricIndex + 1, state.lyricTotal);
    uiText(120, 34, p, F_REG, theme.secondary, 2);
  }

  uiTextFit(64, 56 + slide / 3, state.lyricPrev, F_REG, uiFade(theme.text, 0.38f), 112, 1);
  int block = lyN * 18, first = 96 - block / 2 + 13 + slide;
  for (int i = 0; i < lyN; i++)
    uiText(64, first + i * 18, lyLines[i], F_BOLD, uiFade(accent, 0.25f + 0.75f * t), 1);
  uiTextFit(64, 146 + slide / 2, state.lyricNext, F_REG, uiFade(theme.text, 0.38f * t + 0.1f), 112, 1);
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

  const float cx = 64, cy = 72, th = 6;
  const float rr[3] = {46, 37, 28};
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
  uiText(cx, 62, names[idx], F_REG, uiFade(theme.secondary, fade), 1);
  char v[12];
  if (raw[idx] < 0) snprintf(v, sizeof(v), "n/a"); else snprintf(v, sizeof(v), "%d%%", (int)(vals[idx] + 0.5f));
  uiText(cx, 82, v, F_BIG, uiFade(cols[idx], fade), 1);
  char sub[16] = "";
  if (idx == 0) { float tt = state.cpuTemp >= 0 ? state.cpuTemp : state.thermalZone; if (tt >= 0) snprintf(sub, sizeof(sub), "%dC", (int)tt); }
  if (idx == 1 && state.gpuVramMb > 0) snprintf(sub, sizeof(sub), "%.0fG", state.gpuVramMb / 1024.0f);
  if (idx == 2 && state.gpuTemp >= 0) snprintf(sub, sizeof(sub), "%dC", (int)state.gpuTemp);
  if (sub[0]) uiText(cx, 96, sub, F_REG, uiFade(theme.text, fade * 0.8f), 1);

  const int xs[3] = {24, 64, 104};
  for (int i = 0; i < 3; i++) {
    char t[10]; if (raw[i] < 0) snprintf(t, sizeof(t), "--"); else snprintf(t, sizeof(t), "%d%%", (int)(vals[i] + 0.5f));
    uiText(xs[i], 137, t, F_BOLD, cols[i], 1);
    uiText(xs[i], 150, names[i], F_REG, i == idx ? theme.text : theme.secondary, 1);
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
  uiCard(8, 22, 112, 44, 10, uiCardCol(), theme.text, 34, 255, uiLerp(uiCardCol(), theme.accent, 34), true);
  uiText(16, 36, "TEMPERATURE", F_REG, theme.secondary);
  char tb[12];
  if (haveT) snprintf(tb, sizeof(tb), "%.1f", dTemp); else snprintf(tb, sizeof(tb), "--.-");
  uiText(16, 60, tb, F_HUGE, theme.text);
  uiText(16 + uiW(tb, F_HUGE) + 5, 60, "C", F_BIG, theme.accent);

  // humidity ring card
  uiPanel(8, 70, 54, 40, 10);
  uiArc(35, 90, 15, 4.5f, 1.0f, uiTrackCol());
  uiArc(35, 90, 15, 4.5f, dHum / 100.0f, theme.success);
  char hb[8]; if (haveH) snprintf(hb, sizeof(hb), "%d", (int)(dHum + 0.5f)); else snprintf(hb, sizeof(hb), "--");
  uiText(35, 95, hb, F_BOLD, theme.text, 1);

  // pressure card
  uiPanel(66, 70, 54, 40, 10);
  char pb[10]; if (haveP) snprintf(pb, sizeof(pb), "%d", (int)(dPress + 0.5f)); else snprintf(pb, sizeof(pb), "--");
  uiText(93, 92, pb, F_BIG, theme.text, 1);
  uiText(93, 105, "hPa", F_REG, theme.secondary, 1);

  // microphone waveform card
  if (uiNowMs - micHistMs > 70) {
    micHistMs = uiNowMs;
    for (int i = 0; i < 19; i++) micHist[i] = micHist[i + 1];
    micHist[19] = sensors.micOk ? (float)sensors.micLevel : 0;
  }
  uiPanel(8, 114, 112, 24, 10);
  for (int i = 0; i < 20; i++) {
    float h = 3.0f + (micHist[i] / 100.0f) * 16.0f;
    uint16_t c = uiLerp(theme.accent, theme.warning, (uint8_t)(uiClamp01(micHist[i] / 100.0f) * 255));
    uiCard(16 + i * 5, 126 - h / 2, 3, h, 1.5f, sensors.micOk ? c : uiTrackCol(), c, 0);
  }

  char bl[32]; int bp = batteryPercent();
  if (bp == -2) snprintf(bl, sizeof(bl), "USB power");
  else if (bp == -1) snprintf(bl, sizeof(bl), "No battery");
  else snprintf(bl, sizeof(bl), "%.1fV  %d%%", sensors.batteryVoltage, bp);
  uiText(64, 150, bl, F_REG, theme.secondary, 1);
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
    uiArc(64, 72, 24, 5, 1.0f, uiLerp(theme.bg, theme.success, 90));
    float k = uiEaseOut((uiNowMs % 4000) / 700.0f);
    sprite.drawLine(54, 73, 61, 80, theme.success);
    sprite.drawLine(54, 74, 61, 81, theme.success);
    sprite.drawLine(61, 80, 75, 64, theme.success);
    sprite.drawLine(61, 81, 75, 65, theme.success);
    uiAnnulus(64, 72, 24 + k * 8, 24 + k * 8 - 1.2f, theme.success, (uint8_t)((1 - k) * 110));
    uiText(64, 122, "All clear", F_BOLD, theme.text, 1);
    uiText(64, 140, "Alerts will show up here", F_REG, theme.secondary, 1);
    uiPageDots();
    return;
  }

  int shown = noteCount < 3 ? noteCount : 3;
  for (int i = 0; i < shown; i++) {
    float t = uiEaseOut(((uiNowMs - uiNoteMs) / 1000.0f - i * 0.09f) / 0.38f);
    int ox = (int)((1.0f - t) * 130.0f);
    int y = 22 + i * 40;
    const Note& n = notes[i];
    uint16_t pc = n.priority >= 3 ? theme.danger : (n.priority == 2 ? theme.warning : theme.accent);
    uiCard(8 + ox, y, 112, 36, 10, uiCardCol(), theme.text, 34);
    uiCard(8 + ox, y + 8, 3, 20, 1.5f, n.read ? uiTrackCol() : pc, pc, 0);
    if (!n.read) {
      float g = 0.5f + 0.5f * sinf(uiNowMs / 300.0f);
      uiDisc(110 + ox, y + 10, 5.0f + g, pc, 60);
      uiDisc(110 + ox, y + 10, 3.0f, pc);
    }
    uiTextFit(18 + ox, y + 15, n.title, F_BOLD, n.read ? theme.secondary : theme.text, 84);
    uiTextFit(18 + ox, y + 30, n.message, F_REG, theme.secondary, 94);
  }
  char f[32];
  if (noteCount > shown) snprintf(f, sizeof(f), "+%d more  -  SELECT: read", noteCount - shown);
  else snprintf(f, sizeof(f), "SELECT: mark as read");
  uiText(64, 148, f, F_REG, theme.secondary, 1);
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
  const float cx = 64, cy = 72, r = 45, th = 8;
  if (pomodoro.running) {
    float g = 0.5f + 0.5f * sinf(uiNowMs / 420.0f);
    uiAnnulus(cx, cy, r + th / 2 + 4 + g * 2, r - th / 2 - 4 - g * 2, col, (uint8_t)(10 + 14 * g));
  }
  uiArc(cx, cy, r, th, 1.0f, uiTrackCol());
  uiArc(cx, cy, r, th, uiPomoF, col);

  char tb[8]; snprintf(tb, sizeof(tb), "%02d:%02d", pomodoro.remaining / 60, pomodoro.remaining % 60);
  uiText(cx, 62, pomodoro.isBreak ? "BREAK" : "FOCUS", F_REG, theme.secondary, 1);
  uiText(cx, 84, tb, F_BIG, pomodoro.running ? theme.text : uiLerp(theme.bg, theme.text, 190), 1);
  int done = pomodoro.session % 4;
  for (int i = 0; i < 4; i++) {
    uiDisc(cx - 13.5f + i * 9, 95, 2.5f, i < done ? col : uiTrackCol());
  }

  const char* st = pomodoro.running ? "RUNNING" : "PAUSED";
  uint16_t sc = pomodoro.running ? theme.success : theme.warning;
  int pw = uiW(st, F_BOLD) + 20;
  uiPill(64 - pw / 2, 122, 17, st, F_BOLD, sc, uiLerp(theme.bg, sc, 44), 10);
  uiText(64, 149, pomodoro.running ? "SELECT: pause" : "SELECT: start", F_REG, theme.secondary, 1);
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

  for (int a = 0; a < 3; a++) {
    for (int i = 0; i < 59; i++) scopeH[a][i] = scopeH[a][i + 1];
  }
  scopeH[0][59] = sensors.accelX; scopeH[1][59] = sensors.accelY; scopeH[2][59] = sensors.accelZ - 9.81f;

  if (inspectResultReady) {
    bool normal = inspectResultClass[0] == 'N';
    uint16_t c = normal ? theme.success : theme.danger;
    uiPill(8, 22, 18, normal ? "HEALTHY" : "FAULT", F_BOLD, c, uiLerp(theme.bg, c, 46));
    char cls[28]; uiClean(cls, sizeof(cls), inspectResultClass);
    const GFXfont* f = uiW(cls, F_BIG) <= 112 ? F_BIG : F_BOLD;
    uiTextFit(8, 62, cls, f, theme.text, 112);
    uiPanel(8, 72, 112, 62, 12);
    uiSmooth(uiInspF, inspectResultConf, 6.0f);
    uiArc(36, 103, 20, 6, 1.0f, uiTrackCol());
    uiArc(36, 103, 20, 6, uiInspF, c);
    char pb[8]; snprintf(pb, sizeof(pb), "%d%%", (int)(uiInspF * 100 + 0.5f));
    uiText(36, 108, pb, F_BOLD, theme.text, 1);
    uiText(92, 94, "WORST AXIS", F_REG, theme.secondary, 1);
    uiText(92, 124, inspectResultAxis, F_HUGE, c, 1);
    uiText(64, 150, "SELECT: new capture", F_REG, theme.secondary, 1);
    return;
  }
  if (inspectCapturing) {
    float target = (float)inspectCount / INSPECT_SAMPLES;
    uiSmooth(uiInspF, target, 10.0f);
    uiArc(64, 76, 44, 8, 1.0f, uiTrackCol());
    uiArc(64, 76, 44, 8, uiInspF, theme.warning);
    char nb[16]; snprintf(nb, sizeof(nb), "%d", inspectCount);
    uiText(64, 82, nb, F_HUGE, theme.text, 1);
    uiText(64, 100, "samples", F_REG, theme.secondary, 1);
    uiText(64, 141, "Capturing...", F_BOLD, theme.warning, 1);
    return;
  }

  uiInspF = 0;
  uiPanel(8, 22, 112, 76, 10);
  sprite.drawFastHLine(14, 60, 100, uiLerp(uiCardCol(), theme.text, 50));
  uint16_t sc[3] = {theme.accent, theme.success, theme.warning};
  for (int a = 0; a < 3; a++) {
    for (int i = 0; i < 59; i++) {
      float y0 = uiClamp(60 - scopeH[a][i] * 2.6f, 26, 94), y1 = uiClamp(60 - scopeH[a][i + 1] * 2.6f, 26, 94);
      sprite.drawLine(14 + i * 100 / 59, (int)y0, 14 + (i + 1) * 100 / 59, (int)y1, sc[a]);
    }
  }
  const char* ax[3] = {"X", "Y", "Z"};
  for (int a = 0; a < 3; a++) { uiDisc(18 + a * 22, 90, 2.4f, sc[a]); uiText(24 + a * 22, 94, ax[a], F_REG, theme.secondary); }

  uiChip(8, 104, 54, sensors.adxlOk ? theme.success : theme.danger, "ADXL");
  uiChip(66, 104, 54, sensors.bmeOk ? theme.success : theme.danger, "BME");
  float p = 0.5f + 0.5f * sinf(uiNowMs / 380.0f);
  uiDisc(22, 136, 3.0f + p, theme.accent, 70);
  uiDisc(22, 136, 3.0f, theme.accent);
  uiText(32, 141, "SELECT: start capture", F_REG, theme.text);
  uiText(32, 156, "MODE: back to desk", F_REG, theme.secondary);
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

  // fade instead of jumping
  static float cur = -1;
  if (cur < 0) cur = (float)target;
  cur += (target - cur) * 0.12f;
  int out = (int)(cur + 0.5f);
  if (out != lastBacklight) { analogWrite(PIN_TFT_BL, out); lastBacklight = out; }
}

static void uiPush(const uint16_t* buf) {
  tft.drawRGBBitmap(0, 0, (uint16_t*)buf, UI_W, UI_H);
}

static void uiAllocTransitionBuffers() {
  if (uiPrevBuf || uiCompBuf) return;
  size_t sz = UI_W * UI_H * sizeof(uint16_t);
  uiPrevBuf = (uint16_t*)(psramFound() ? ps_malloc(sz) : malloc(sz));
  uiCompBuf = (uint16_t*)(psramFound() ? ps_malloc(sz) : malloc(sz));
  if (!uiPrevBuf || !uiCompBuf) {
    if (uiPrevBuf) free(uiPrevBuf);
    if (uiCompBuf) free(uiCompBuf);
    uiPrevBuf = uiCompBuf = nullptr;
  }
}

// Renders the current screen into the sprite. Exposed separately so it can be
// run off-device (host preview) without a TFT.
static void uiRenderPage() {
  if (mode == MODE_INSPECTION) { drawInspectionPage(); return; }
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
}

static const uint16_t* uiFrame(unsigned long now) {
  uiNowMs = now;
  uiDt = uiLastFrameMs ? uiClamp((now - uiLastFrameMs) / 1000.0f, 0.001f, 0.1f) : 0.033f;
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

void drawTft(unsigned long now) {
  updateBacklight(now);
  if (state.backendOnline && strcmp(state.sleepStage, "deep_sleep") == 0 && !wakeActive(now) && mode != MODE_INSPECTION) {
    return;  // screen is dark in deep sleep; skip the work
  }
  tftFullRedraw = false;
  uiPush(uiFrame(now));
}

// ----------------------------------------------------------------------------
// Boot animation (replaces the old text boot screen on the TFT)
// ----------------------------------------------------------------------------
void uiBoot() {
  unsigned long t0 = millis(), last = t0;
  while (true) {
    unsigned long now = millis();
    float t = (now - t0) / 1500.0f;
    if (t >= 1.0f) break;
    uiNowMs = now; uiDt = uiClamp((now - last) / 1000.0f, 0.001f, 0.1f); last = now;
    uiBackground(theme.accent, 70);
    float e = uiEaseOut(t * 1.3f);
    uiArc(64, 62, 26, 6, 1.0f, uiTrackCol());
    uiArc(64, 62, 26, 6, 0.08f + 0.9f * e, theme.accent, 255, t * 9.0f);
    uiDisc(64, 62, 4.0f + 1.5f * sinf(t * 14.0f), theme.text, (uint8_t)(255 * uiClamp01(t * 3)));
    float a1 = uiClamp01((t - 0.25f) / 0.3f), a2 = uiClamp01((t - 0.45f) / 0.3f);
    uiText(64, 118 + (int)((1 - a1) * 8), "DeskBuddy", F_BIG, uiFade(theme.text, a1), 1);
    uiText(64, 136, "PC-aware desk companion", F_REG, uiFade(theme.secondary, a2), 1);
    uiText(64, 152, "v" FW_VERSION, F_REG, uiFade(theme.secondary, a2 * 0.7f), 1);
    uiPush(uiFb());
    delay(6);
  }
}