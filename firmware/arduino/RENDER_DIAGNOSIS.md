# ST7735 Text Rendering Diagnosis

## Result

The scattering was **not** a driver, SPI, sprite-allocation, or concurrency
problem. It was a bug in the custom 4-bit anti-aliased glyph decoder:

> Each glyph row is padded to a whole byte by `font_converter_aa.py`, but the
> nibble selector used a *continuous* `(row * width + col)` index. Whenever a
> glyph had an odd width (45 of 95 glyphs in Inter_14), the high/low nibble
> order was inverted on every other row. The result was pixel strips swapped
> inside each glyph, which reads as scattered / fragmented characters.

A second, independent corruption path existed in the title marquee: it drew a
4-bit font through Adafruit GFX's **1-bit** `print()` renderer.

## Evidence

`parity_before_after.png` is produced from the exact `Inter_14.h` data using the
firmware algorithm.

- Top line: old `(row * width + col) % 2` selector -> shredded.
- Bottom line: `(col & 1)` selector -> clean.

The same comparison was rendered on the physical panel as Stage E of
`RenderDiag` (red = old, green = new). Observed result:

| Stage E half | Physical result |
|---|---|
| Old parity (red) | shredded / scattered |
| Fixed parity (green) | clean and readable |

`marquee_clip.png` shows the clipped marquee renderer at three scroll offsets.
It stays inside its 120 px window at every offset.

## Diagnostic matrix

| Test | Pipeline | Result |
|---|---|---|
| A | U8g2 -> TFT directly | Pass |
| B | U8g2 -> GFXcanvas16 -> TFT | Pass |
| C | Built-in GFX font -> GFXcanvas16 -> TFT | Pass |
| D | Custom 4-bit AA -> GFXcanvas16 -> TFT (fixed) | Pass |
| E | Old vs fixed nibble parity, same font data | Old fail, fixed pass |
| F | Clipped marquee scroll | Pass (offline strip; sketch available) |

A, B and C only exercise the 1-bit/U8g2 paths, which is why they kept passing
while production text stayed broken.

## Why the previous stride fix was incomplete

Commit `513c635` corrected the byte address:

```cpp
bo + row * ((gw + 1) / 2) + (col / 2)   // correct
```

but left the nibble selector as:

```cpp
if ((row * gw + col) % 2 == 0)          // wrong for odd-width rows
```

The address and the nibble order must use the same per-row model.

## Minimal fix

`firmware/arduino/DeskBuddy_Companion/ui_modern.h`

1. Added `uiTextAARect()`: one 4-bit glyph decoder that can target any
   `GFXcanvas16` and can be clipped horizontally.
2. Nibble order is per-row: `(c & 1) ? low nibble : high nibble`.
3. `uiTextAA()` is now a thin wrapper over `uiTextAARect(&sprite, ...)`.
4. `uiMarquee()` uses `uiTextAARect()` for face modes `>= 4` instead of feeding
   4-bit glyph data to the 1-bit `GFXcanvas16::print()` path.

No fonts were replaced, no driver was changed, no PlatformIO migration, and no
sensor/music integrations were touched.

## Files modified

| File | Change |
|---|---|
| `firmware/arduino/DeskBuddy_Companion/ui_modern.h` | Fixed nibble parity; unified AA renderer; fixed 4-bit marquee path |
| `firmware/arduino/RenderDiag/RenderDiag.ino` | New 5-stage (A-F) reproduction/diagnostic sketch |
| `firmware/arduino/RenderDiag/Fonts/Inter_14.h` | Copy of the production font for the standalone sketch |
| `firmware/arduino/RenderDiag/*.png` | Before/after renders |

## Build / verification

- Production sketch: `Sketch uses 551967 bytes (17%)`
- Diagnostic sketch: `Sketch uses 372663 bytes (11%)`
- Backend: `41 passed`
- Physical panel: Stage E confirmed old = shredded, fixed = clean; production
  music page confirmed "all text clean and readable".

## Re-running the diagnostic

Flash `firmware/arduino/RenderDiag` and watch for ~75 s:
A (8 s), B (8 s), C (8 s), D (10 s), E (10 s), F (12 s). Serial at 115200 prints
one line per stage.

## Note on the perimeter ring

The perimeter progress ring remains disabled. It is unrelated to this bug and
should be reintroduced separately with bounded/clipped drawing after the text
pipeline is stable.
