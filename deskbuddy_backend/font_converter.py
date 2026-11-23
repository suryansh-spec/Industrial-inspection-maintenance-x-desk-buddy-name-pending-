"""
Convert TTF/OTF fonts to Adafruit GFX font format.
Usage: python font_converter.py <font.ttf> <size_px> <output.h> <font_name>
"""
import sys
from PIL import Image, ImageFont, ImageDraw

def convert_font(ttf_path, size, output_path, font_name):
    font = ImageFont.truetype(ttf_path, size)
    
    # First pass: measure all glyphs
    glyphs = []
    bitmaps = bytearray()
    
    first_char = 32
    last_char = 126
    
    # Get font metrics
    ascent, descent = font.getmetrics()
    y_advance = ascent + descent
    
    for char_code in range(first_char, last_char + 1):
        char = chr(char_code)
        
        # Render character
        bbox = font.getbbox(char)
        if bbox is None:
            # Empty glyph (space)
            glyphs.append({
                'bitmapOffset': len(bitmaps),
                'width': 0,
                'height': 0,
                'xAdvance': font.getlength(char),
                'xOffset': 0,
                'yOffset': 0,
            })
            continue
        
        x0, y0, x1, y1 = bbox
        w = x1 - x0
        h = y1 - y0
        
        # Render to image
        img = Image.new('L', (w, h), 0)
        draw = ImageDraw.Draw(img)
        draw.text((-x0, -y0), char, font=font, fill=255)
        
        # Pack bits MSB first, row by row
        bitmap_offset = len(bitmaps)
        for row in range(h):
            byte_val = 0
            bit_pos = 7
            for col in range(w):
                if img.getpixel((col, row)) > 127:
                    byte_val |= (1 << bit_pos)
                bit_pos -= 1
                if bit_pos < 0:
                    bitmaps.append(byte_val)
                    byte_val = 0
                    bit_pos = 7
            if bit_pos != 7:
                bitmaps.append(byte_val)
        
        glyphs.append({
            'bitmapOffset': bitmap_offset,
            'width': w,
            'height': h,
            'xAdvance': font.getlength(char),
            'xOffset': x0,
            'yOffset': y0 - ascent,  # Offset from baseline
        })
    
    # Generate C header
    with open(output_path, 'w') as f:
        f.write(f'#pragma once\n')
        f.write(f'#include <Adafruit_GFX.h>\n\n')
        f.write(f'// {font_name} {size}pt - converted from TTF\n\n')
        
        # Bitmap array
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
                    f'{int(g["xAdvance"])}, {g["xOffset"]}, {g["yOffset"]}}},\n')
        f.write('};\n\n')
        
        # Font struct
        f.write(f'const GFXfont {font_name} PROGMEM = {{\n')
        f.write(f'    (uint8_t *){font_name}Bitmaps,\n')
        f.write(f'    (GFXglyph *){font_name}Glyphs,\n')
        f.write(f'    {first_char}, {last_char}, {y_advance}\n')
        f.write('};\n')
    
    print(f'Generated {output_path}: {len(bitmaps)} bytes, {len(glyphs)} glyphs, yAdvance={y_advance}')

if __name__ == '__main__':
    if len(sys.argv) < 5:
        print('Usage: python font_converter.py <font.ttf> <size_px> <output.h> <font_name>')
        sys.exit(1)
    
    convert_font(sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4])