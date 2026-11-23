"""
Convert TTF/OTF fonts to 4-bit anti-aliased Adafruit GFX font format.
Usage: python font_converter_aa.py <font.ttf> <size_px> <output.h> <font_name>
"""
import sys
from PIL import Image, ImageFont, ImageDraw

def convert_font(ttf_path, size, output_path, font_name):
    font = ImageFont.truetype(ttf_path, size)
    
    glyphs = []
    bitmaps = bytearray()
    
    first_char = 32
    last_char = 126
    
    ascent, descent = font.getmetrics()
    y_advance = ascent + descent
    
    for char_code in range(first_char, last_char + 1):
        char = chr(char_code)
        
        # Render character to large image first
        img_large = Image.new('L', (64, 64), 0)
        draw = ImageDraw.Draw(img_large)
        draw.text((0, 0), char, font=font, fill=255)
        
        bbox = img_large.getbbox()
        if bbox is None:
            glyphs.append({
                'bitmapOffset': len(bitmaps),
                'width': 0,
                'height': 0,
                'xAdvance': int(font.getlength(char)),
                'xOffset': 0,
                'yOffset': 0,
            })
            continue
        
        x0, y0, x1, y1 = bbox
        w = x1 - x0
        h = y1 - y0
        
        img = img_large.crop(bbox)
        
        # Pack 4-bit grayscale, 2 pixels per byte, MSB first
        bitmap_offset = len(bitmaps)
        for row in range(h):
            for col in range(0, w, 2):
                val1 = img.getpixel((col, row)) if col < w else 0
                val2 = img.getpixel((col + 1, row)) if col + 1 < w else 0
                gray1 = val1 >> 4
                gray2 = val2 >> 4
                packed = (gray1 << 4) | gray2
                bitmaps.append(packed)
        
        glyphs.append({
            'bitmapOffset': bitmap_offset,
            'width': w,
            'height': h,
            'xAdvance': int(font.getlength(char)),
            'xOffset': x0,
            'yOffset': y0 - ascent,
        })
    
    # Generate C header with 4-bit grayscale data
    with open(output_path, 'w') as f:
        f.write(f'#pragma once\n')
        f.write(f'#include <Adafruit_GFX.h>\n\n')
        f.write(f'// {font_name} {size}pt - 4-bit anti-aliased, converted from TTF\n\n')
        
        # Bitmap array (4-bit grayscale, 2 pixels per byte)
        f.write(f'const uint8_t {font_name}Bitmaps[] PROGMEM = {{\n')
        for i, b in enumerate(bitmaps):
            if i % 16 == 0:
                f.write('    ')
            f.write(f'0x{b:02X}, ')
            if i % 16 == 15:
                f.write('\n')
        if len(bitmaps) % 16 != 0:
            f.write('\n')
        f.write('};\n\n')
        
        # Glyph array
        f.write(f'const GFXglyph {font_name}Glyphs[] PROGMEM = {{\n')
        for g in glyphs:
            f.write(f'    {{{g["bitmapOffset"]}, {g["width"]}, {g["height"]}, '
                    f'{g["xAdvance"]}, {g["xOffset"]}, {g["yOffset"]}}},\n')
        f.write('};\n\n')
        
        # Font struct (same as GFXfont, but data is 4-bit)
        f.write(f'const GFXfont {font_name} PROGMEM = {{\n')
        f.write(f'    (uint8_t *){font_name}Bitmaps,\n')
        f.write(f'    (GFXglyph *){font_name}Glyphs,\n')
        f.write(f'    {first_char}, {last_char}, {y_advance}\n')
        f.write('};\n')
    
    print(f'Generated {output_path}: {len(bitmaps)} bytes (4-bit), {len(glyphs)} glyphs, yAdvance={y_advance}')

if __name__ == '__main__':
    if len(sys.argv) < 5:
        print('Usage: python font_converter_aa.py <font.ttf> <size_px> <output.h> <font_name>')
        sys.exit(1)
    
    convert_font(sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4])