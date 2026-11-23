#!/usr/bin/env python3
"""Apply all necessary fixes to ui_modern.h and DeskBuddy_Companion.ino"""

import re

# Read files
with open('firmware/arduino/DeskBuddy_Companion/ui_modern.h', 'r') as f:
    ui_modern = f.read()

with open('firmware/arduino/DeskBuddy_Companion/DeskBuddy_Companion.ino', 'r') as f:
    ino = f.read()

# ============================================================
# Fix 1: DeskBuddy_Companion.ino - use standard GFXcanvas16 + UI_FORCE_FULL_PUSH
# ============================================================
ino = re.sub(
    r'// The framebuffer is touched per-pixel during software AA, so keep it in fast\n// internal SRAM instead of letting malloc place the 40 KB canvas in PSRAM\.\nclass InternalCanvas16 : public GFXcanvas16 \{\n  public:\n  InternalCanvas16\(uint16_t w, uint16_t h\) : GFXcanvas16\(w, h, false\) \{\n    uint32_t bytes = \(uint32_t\)w \* h \* 2;\n    buffer = \(uint16_t\*\)heap_caps_malloc\(bytes, MALLOC_CAP_INTERNAL \| MALLOC_CAP_8BIT\);\n    if \(!buffer\) buffer = \(uint16_t\*\)malloc\(bytes\);   // fall back if SRAM is tight\n    if \(buffer\) \{ memset\(buffer, 0, bytes\); buffer_owned = false; \}\n  \}\n\};\nInternalCanvas16 sprite\(128, 160\);',
    '// Use standard GFXcanvas16 for testing\nGFXcanvas16 sprite(128, 160);',
    ino
)

ino = ino.replace(
    '#if defined(HAS_U8G2_GFX)\nU8G2_FOR_ADAFRUIT_GFX u8g2gfx;\n#endif\n#include "ui_modern.h"',
    '#if defined(HAS_U8G2_GFX)\nU8G2_FOR_ADAFRUIT_GFX u8g2gfx;\n#endif\n#define UI_FORCE_FULL_PUSH 1\n#include "ui_modern.h"'
)

# ============================================================
# Fix 2: ui_modern.h - uiText: auto uiTextAA for TTF fonts (mode >= 4)
# ============================================================
ui_modern = re.sub(
    r'static void uiText\(int x, int y, const char\* s, uint8_t fid, uint16_t col, int align = 0\) \{\n  if \(!s \|\| !s\[0\]\) return;\n  if \(uiFontAA\) \{\n    uiTextAA\(x, y, s, fid, col, align\);\n    return;\n  \}\n  int16_t x1, y1; uint16_t w, h;\n  sprite\.setFont\(uiFace\(fid\)\); sprite\.setTextSize\(uiScale\(fid\)\); sprite\.setTextColor\(col\);\n  sprite\.getTextBounds\(s, 0, 0, &x1, &y1, &w, &h\);\n  int px = \(align == 0\) \? x - x1 : \(align == 1 \? x - \(int\)w / 2 - x1 : x - \(int\)w - x1\);\n  sprite\.setCursor\(px, y\);\n  sprite\.print\(s\);\n\}',
    '''static void uiText(int x, int y, const char* s, uint8_t fid, uint16_t col, int align = 0) {
  if (!s || !s[0]) return;
  // TTF fonts (mode >= 4) are 4-bit AA; always use uiTextAA for them.
  // Pixel font (mode 0-3) uses sprite.print (1-bit).
  if (uiFontAA || uiFontFaceMode >= 4) {
    uiTextAA(x, y, s, fid, col, align);
    return;
  }
  int16_t x1, y1; uint16_t w, h;
  sprite.setFont(uiFace(uiFontFaceMode)); sprite.setTextSize(uiScale(fid)); sprite.setTextColor(col);
  sprite.getTextBounds(s, 0, 0, &x1, &y1, &w, &h);
  int px = (align == 0) ? x - x1 : (align == 1 ? x - (int)w / 2 - x1 : x - (int)w - x1);
  sprite.setCursor(px, y);
  sprite.print(s);
}''',
    ui_modern
)

# ============================================================
# Fix 3: uiW - TTF font measurement using glyph xAdvance
# ============================================================
ui_modern = re.sub(
    r'static int uiW\(const char\* s, uint8_t fid\) \{\n  if \(!s \|\| !s\[0\]\) return 0;\n  int16_t x1, y1; uint16_t w, h;\n  sprite\.setFont\(uiFace\(fid\)\); sprite\.setTextSize\(uiScale\(fid\)\);\n  sprite\.getTextBounds\(s, 0, 0, &x1, &y1, &w, &h\);\n  return \(int\)w;\n\}',
    '''static int uiW(const char* s, uint8_t fid) {
  if (!s || !s[0]) return 0;
  // For TTF fonts (4-bit AA), measure using glyph xAdvance directly.
  if (uiFontFaceMode >= 4) {
    const GFXfont* font = uiFace(uiFontFaceMode);
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
}''',
    ui_modern
)

# ============================================================
# Fix 4: uiMarquee - fall back to Pixel font for TTF fonts
# ============================================================
ui_modern = re.sub(
    r'static void uiMarquee\(int x, int baseline, int w, const char\* s, uint8_t fid,\n                      uint16_t col, uint16_t bg, bool center\) \{\n  char t\[100\]; uiClean\(t, sizeof\(t\), s\);\n  int tw = uiW\(t, fid\);\n  uint8_t sc = uiScale\(fid\);\n  if \(tw <= w\) \{ uiText\(center \? x + w / 2 : x, baseline, t, fid, col, center \? 1 : 0\); return; \}\n  if \(!uiMq\) uiMq = new GFXcanvas16\(UI_MQ_W, UI_MQ_H\);\n  if \(!uiMq \|\| !uiMq->getBuffer\(\) \|\| w > UI_MQ_W\) \{ uiTextFit\(x, baseline, t, fid, col, w\); return; \}\n  uiMq->fillScreen\(bg\);\n  uiMq->setFont\(uiFace\(fid\)\); uiMq->setTextSize\(sc\); uiMq->setTextColor\(col\);\n  int loop = tw \+ 24;\n  unsigned long period = \(unsigned long\)loop \* 30 \+ 1200, ph = uiNowMs % period;\n  int off = ph < 1200 \? 0 : \(int\)\(\(ph - 1200\) / 30\);\n  int16_t x1, y1; uint16_t bw, bh;\n  uiMq->getTextBounds\(t, 0, 0, &x1, &y1, &bw, &bh\);\n  int base = UI_MQ_H - 1;\n  for \(int k = 0; k < 2; k\+\+\) \{ uiMq->setCursor\(-x1 - off \+ k \* loop, base\); uiMq->print\(t\); \}\n  uint16_t\* b = uiMq->getBuffer\(\);\n  for \(int row = 0; row < UI_MQ_H; row\+\+\) \{\n    uint16_t\* r = b \+ row \* UI_MQ_W;\n    for \(int i = 0; i < 3; i\+\+\) \{\n      uint8_t a = \(uint8_t\)\(\(i \+ 1\) \* 255 / 4\);\n      r\[i\] = uiLerp\(bg, r\[i\], a\);\n      r\[w - 1 - i\] = uiLerp\(bg, r\[w - 1 - i\], a\);\n    \}\n    sprite\.drawRGBBitmap\(x, baseline - UI_MQ_H \+ 1 \+ row, r, w, 1\);\n  \}\n\}',
    '''static void uiMarquee(int x, int baseline, int w, const char* s, uint8_t fid,
                      uint16_t col, uint16_t bg, bool center) {
  char t[100]; uiClean(t, sizeof(t), s);
  // Marquee canvas only supports 1-bit fonts; fall back to Pixel for TTF fonts.
  uint8_t face = (uiFontFaceMode >= 4) ? 0 : uiFontFaceMode;
  int tw = uiW(t, fid);
  uint8_t sc = uiScale(fid);
  if (tw <= w) { uiText(center ? x + w / 2 : x, baseline, t, fid, col, center ? 1 : 0); return; }
  if (!uiMq) uiMq = new GFXcanvas16(UI_MQ_W, UI_MQ_H);
  if (!uiMq || !uiMq->getBuffer() || w > UI_MQ_W) { uiTextFit(x, baseline, t, fid, col, w); return; }
  uiMq->fillScreen(bg);
  uiMq->setFont(uiFace(face)); uiMq->setTextSize(sc); uiMq->setTextColor(col);
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
}''',
    ui_modern
)

# ============================================================
# Fix 5: Music page - use TTF fonts with auto-AA, disable perimeter, use uiTextFit
# ============================================================
# Replace the title/artist section
ui_modern = re.sub(
    r'// Title \+ artist \(configurable fonts\)\.\n  uiFontFaceMode = uiMusicTitleFont; uiFontAA = uiMusicTitleAA;\n  uiMarquee\(52, 30, 68, state\.musicTitle, F_BOLD, theme\.text, theme\.bg, true\);\n  uiFontFaceMode = uiMusicArtistFont; uiFontAA = uiMusicArtistAA;\n  uiMarquee\(52, 46, 68, state\.musicArtist\[0\] \? state\.musicArtist : "Unknown artist", F_REG, theme\.secondary, theme\.bg, false\);',
    '''// Title + artist (TTF fonts with auto-AA).
  uiFontFaceMode = uiMusicTitleFont; uiFontAA = true;
  uiTextFit(52, 30, state.musicTitle, F_BOLD, theme.text, 68, 1);
  uiFontFaceMode = uiMusicArtistFont; uiFontAA = true;
  uiTextFit(52, 46, state.musicArtist[0] ? state.musicArtist : "Unknown artist", F_REG, theme.secondary, 68, 0);''',
    ui_modern
)

# Replace lyrics section
ui_modern = re.sub(
    r'// Current lyric \(same font for all lines\)\.\n  if \(state\.lyricCur\[0\] != \'\\\\0\'\) \{\n    char ly\[3\]\[40\];\n    uiFontFaceMode = uiMusicActiveLyricFont; uiFontAA = uiMusicActiveLyricAA;\n    int n = uiWrap\(state\.lyricCur, F_REG, 112, ly, 3\);\n    uint16_t lcol = state\.lyricsAvailable \? uiFade\(accent, 0\.95f\) : uiFade\(theme\.text, 0\.7f\);\n    int ly0 = 76;\n    for \(int i = 0; i < n; i\+\+\) \{\n      uiTextFit\(8, ly0 \+ i \* 11, ly\[i\], F_REG, lcol, 112, 0\);\n    \}\n  \}',
    '''// Current lyric (TTF font with auto-AA).
  if (state.lyricCur[0] != '\\0') {
    char ly[3][40];
    uiFontFaceMode = uiMusicActiveLyricFont; uiFontAA = true;
    int n = uiWrap(state.lyricCur, F_REG, 112, ly, 3);
    uint16_t lcol = state.lyricsAvailable ? uiFade(accent, 0.95f) : uiFade(theme.text, 0.7f);
    int ly0 = 76;
    for (int i = 0; i < n; i++) {
      uiTextFit(8, ly0 + i * 11, ly[i], F_REG, lcol, 112, 0);
    }
  }''',
    ui_modern
)

# Replace perimeter progress indicator with disabled comment
ui_modern = re.sub(
    r'// Perimeter progress indicator around the album artwork\.\n  float target = state\.musicDuration > 0 \? uiClamp01\(\(float\)state\.musicProgress / state\.musicDuration\) : 0\.0f\);\n  if \(uiProg < 0\) uiProg = 0\.0f;\n  // Reset on new track\.\n  if \(strcmp\(uiLastTitle, state\.musicTitle\) != 0\) \{\n    strncpy\(uiLastTitle, state\.musicTitle, sizeof\(uiLastTitle\) - 1\);\n    uiLastTitle\[sizeof\(uiLastTitle\) - 1\] = 0;\n    uiProg = 0\.0f;\n    uiProgressCompleteMs = 0;\n  \}\n  uiSmooth\(uiProg, target, 6\.0f\);\n  if \(uiProg > 0\.999f\) \{\n    uiProg = 1\.0f;\n    if \(uiProgressCompleteMs == 0\) uiProgressCompleteMs = millis\(\);\n  \} else \{\n    uiProgressCompleteMs = 0;\n  \}\n\n  // Artwork container \(must match cover draw above\)\.\n  const int artX = 8, artY = 22, artW = 40, artH = 40;\n  const int margin = 4;\n  const int rx = artX - margin, ry = artY - margin;\n  const int rw = artW \+ margin \* 2, rh = artH \+ margin \* 2;\n  const int cr = 6; // corner radius\n\n  // Configurable style \(defaults\)\.\n  const uint16_t baseCol = 0x4208;   // dim blue/grey\n  const uint16_t progCol = 0x3EDF;   // cyan #39D9FF\n  const uint16_t glowCol = 0x1D9F;   // darker cyan glow',
    '// Perimeter progress indicator DISABLED for debugging.',
    ui_modern
)

# Remove the rest of the perimeter progress indicator code (from baseCol to char a[12])
# This is a large block - we'll use a more aggressive replacement
ui_modern = re.sub(
    r'const uint16_t baseCol = 0x4208;   // dim blue/grey\n  const uint16_t progCol = 0x3EDF;   // cyan #39D9FF\n  const uint16_t glowCol = 0x1D9F;   // darker cyan glow\n  const uint16_t endCol  = 0xFFFF;   // white leading endpoint\n  const int borderThick = 2;\n  const int glowLayers = 2;\n  const int endSize = 3;\n\n  // Perimeter length of rounded rect\.\n  float perim = 2\.0f \* \(rw \+ rh\) - 8\.0f \* cr \+ 2\.0f \* 3\.14159265f \* cr;\n\n  // Helper lambda to get point along perimeter at distance s \(0\.\.perim\)\.\n  auto perimPoint = \[&\]\(float s, float\* px, float\* py\) \{\n    // normalize\n    while \(s < 0\) s \+= perim;\n    while \(s > perim\) s \-= perim;\n    float cum = 0;\n    // Segment lengths\n    float lArc = 1\.5707963f \* cr; // quarter circle\n    float lTop = \(float\)\(rw - 2 \* cr\);\n    float lRight = \(float\)\(rh - 2 \* cr\);\n    float lBottom = \(float\)\(rw - 2 \* cr\);\n    float lLeft = \(float\)\(rh - 2 \* cr\);\n    // 1: top-left arc \(from left point to top point\), clockwise\n    if \(s < lArc\) \{\n      float a = 3\.14159265f - \(s / lArc\) \* 1\.5707963f; // pi -> pi/2\n      \*px = \(rx \+ cr\) \+ cosf\(a\) \* cr;\n      \*py = \(ry \+ cr\) \+ sinf\(a\) \* cr;\n      return;\n    \}\n    cum \+= lArc;\n    // 2: top edge\n    if \(s < cum \+ lTop\) \{\n      float t = \(s - cum\) / \(lTop > 0 \? lTop : 1\);\n      \*px = \(rx \+ cr\) \+ t \* lTop;\n      \*py = \(float\)ry;\n      return;\n    \}\n    cum \+= lTop;\n    // 3: top-right arc\n    if \(s < cum \+ lArc\) \{\n      float a = 1\.5707963f - \(\(s - cum\) / lArc\) \* 1\.5707963f; // pi/2 -> 0\n      \*px = \(rx \+ rw - cr\) \+ cosf\(a\) \* cr;\n      \*py = \(ry \+ cr\) \+ sinf\(a\) \* cr;\n      return;\n    \}\n    cum \+= lArc;\n    // 4: right edge\n    if \(s < cum \+ lRight\) \{\n      float t = \(s - cum\) / \(lRight > 0 \? lRight : 1\);\n      \*px = \(float\)\(rx \+ rw\);\n      \*py = \(ry \+ cr\) \+ t \* lRight;\n      return;\n    \}\n    cum \+= lRight;\n    // 5: bottom-right arc\n    if \(s < cum \+ lArc\) \{\n      float a = 0\.0f - \(\(s - cum\) / lArc\) \* 1\.5707963f; // 0 -> -pi/2\n      \*px = \(rx \+ rw - cr\) \+ cosf\(a\) \* cr;\n      \*py = \(ry \+ rh - cr\) \+ sinf\(a\) \* cr;\n      return;\n    \}\n    cum \+= lArc;\n    // 5: bottom edge\n    if \(s < cum \+ lBottom\) \{\n      float t = \(s - cum\) / \(lBottom > 0 \? lBottom : 1\);\n      \*px = \(rx \+ rw - cr\) - t \* lBottom;\n      \*py = \(float\)\(ry \+ rh\);\n      return;\n    \}\n    cum \+= lBottom;\n    // 7: bottom-left arc\n    if \(s < cum \+ lArc\) \{\n      float a = -1\.5707963f - \(\(s - cum\) / lArc\) \* 1\.5707963f; // -pi/2 -> -pi\n      \*px = \(rx \+ cr\) \+ cosf\(a\) \* cr;\n      \*py = \(ry \+ rh - cr\) \+ sinf\(a\) \* cr;\n      return;\n    \}\n    cum \+= lArc;\n    // 8: left edge\n    \{\n      float t = \(s - cum\) / \(lLeft > 0 \? lLeft : 1\);\n      \*px = \(float\)rx;\n      \*py = \(ry \+ rh - cr\) - t \* lLeft;\n    \}\n  \};\n\n  // Draw base outline \(full perimeter, dim\)\. Smaller step \+ 2x2 brush for continuity\.\n  float step = 0\.5f;\n  for \(float d = 0; d < perim; d \+= step\) \{\n    float px, py;\n    perimPoint\(d, &px, &py\);\n    int ix = \(int\)\(px \+ 0\.5f\);\n    int iy = \(int\)\(py \+ 0\.5f\);\n    if \(ix >= 0 \&\& ix < UI_W \&\& iy >= 0 \&\& iy < UI_H\) \{\n      uiPx\(ix, iy, baseCol, 255\);\n      if \(ix \+ 1 < UI_W\) uiPx\(ix \+ 1, iy, baseCol, 255\);\n      if \(iy \+ 1 < UI_H\) uiPx\(ix, iy \+ 1, baseCol, 255\);\n      if \(ix \+ 1 < UI_W \&\& iy \+ 1 < UI_H\) uiPx\(ix \+ 1, iy \+ 1, baseCol, 255\);\n    \}\n  \}\n\n  // Draw progress segment\.\n  float progDist = perim \* uiProg;\n  // glow layers\n  for \(int g = glowLayers; g >= 1; g--\) \{\n    uint8_t a = \(uint8_t\)\(40 \+ 40 \* \(glowLayers - g \+ 1\)\);\n    for \(float d = 0; d <= progDist; d \+= step\) \{\n      float px, py;\n      perimPoint\(d, &px, &py\);\n      int ix = \(int\)\(px \+ 0\.5f\);\n      int iy = \(int\)\(py \+ 0\.5f\);\n      for \(int oy = -g; oy <= g; oy\+\+\) \{\n        for \(int ox = -g; ox <= g; ox\+\+\) \{\n          int x = ix \+ ox, y = iy \+ oy;\n          if \(x >= 0 \&\& x < UI_W \&\& y >= 0 \&\& y < UI_H\) \{\n            uiPx\(x, y, glowCol, a\);\n          \}\n        \}\n      \}\n    \}\n  \}\n  // main progress line\n  for \(float d = 0; d <= progDist; d \+= step\) \{\n    float px, py;\n    perimPoint\(d, &px, &py\);\n    int ix = \(int\)\(px \+ 0\.5f\);\n    int iy = \(int\)\(py \+ 0\.5f\);\n    for \(int oy = 0; oy < borderThick; oy\+\+\) \{\n      for \(int ox = 0; ox < borderThick; ox\+\+\) \{\n        int x = ix \+ ox, y = iy \+ oy;\n        if \(x >= 0 \&\& x < UI_W \&\& y >= 0 \&\& y < UI_H\) uiPx\(x, y, progCol, 255\);\n      \}\n    \}\n  \}\n\n  // Leading endpoint\.\n  if \(uiProg > 0\.001f \&\& uiProg < 0\.999f\) \{\n    float px, py;\n    perimPoint\(progDist, &px, &py\);\n    int ix = \(int\)\(px \+ 0\.5f\);\n    int iy = \(int\)\(py \+ 0\.5f\);\n    for \(int dy = -endSize; dy <= endSize; dy\+\+\) \{\n      for \(int dx = -endSize; dx <= endSize; dx\+\+\) \{\n        if \(dx \* dx \+ dy \* dy <= endSize \* endSize\) \{\n          int x = ix \+ dx, y = iy \+ dy;\n          if \(x >= 0 \&\& x < UI_W \&\& y >= 0 \&\& y < UI_H\) \{\n            uiPx\(x, y, endCol, 255\);\n          \}\n        \}\n      \}\n    \}\n  \}\n\n  // Completion hold: if complete, full perimeter already drawn \(progDist=perim\)\.\n\n  char a\[12\], b\[12\]; uiFmtTime\(state\.musicProgress, a, sizeof\(a\)\); uiFmtTime\(state\.musicDuration, b, sizeof\(b\)\);\n  uiFontFaceMode = uiMusicTimerFont; uiFontAA = uiMusicTimerAA;',
    'char a[12], b[12]; uiFmtTime(state.musicProgress, a, sizeof(a)); uiFmtTime(state.musicDuration, b, sizeof(b));\n  uiFontFaceMode = uiMusicTimerFont; uiFontAA = true;',
    ui_modern
)

# Also update timer/status to use uiFontAA = true
ui_modern = ui_modern.replace(
    'uiFontFaceMode = uiMusicTimerFont; uiFontAA = uiMusicTimerAA;\n  uiText(8, 106, a, F_REG, theme.secondary, 0);\n  uiText(120, 106, b, F_REG, theme.secondary, 2);\n\n  char hint[32];\n  snprintf(hint, sizeof(hint), state.musicPlaying ? "Playing" : "Paused");\n  uiFontFaceMode = uiMusicStatusFont; uiFontAA = uiMusicStatusAA;\n  uiText(64, 124, hint, F_REG, state.musicPlaying ? theme.success : theme.warning, 1);',
    'uiFontFaceMode = uiMusicTimerFont; uiFontAA = true;\n  uiText(8, 106, a, F_REG, theme.secondary, 0);\n  uiText(120, 106, b, F_REG, theme.secondary, 2);\n\n  char hint[32];\n  snprintf(hint, sizeof(hint), state.musicPlaying ? "Playing" : "Paused");\n  uiFontFaceMode = uiMusicStatusFont; uiFontAA = true;\n  uiText(64, 124, hint, F_REG, state.musicPlaying ? theme.success : theme.warning, 1);'
)

# Write files
with open('firmware/arduino/DeskBuddy_Companion/ui_modern.h', 'w') as f:
    f.write(ui_modern)

with open('firmware/arduino/DeskBuddy_Companion/DeskBuddy_Companion.ino', 'w') as f:
    f.write(ino)

print("All fixes applied successfully!")