# -*- coding: utf-8 -*-
"""Text-only fallback picons for IPTV streams without any supplied logo.

Small deterministic PNGs generated with stdlib (also Python 2.7).  No external
font, Pillow, ImageMagick or Internet required.  Unlike a station logo this
explicitly represents the display name only.
"""
from __future__ import absolute_import
import struct
import zlib

# Original minimal 5x7 uppercase pixel lettering, 1=ink / 0=background.
GLYPHS = {
'A':['01110','10001','10001','11111','10001','10001','10001'],
'B':['11110','10001','10001','11110','10001','10001','11110'],
'C':['01111','10000','10000','10000','10000','10000','01111'],
'D':['11110','10001','10001','10001','10001','10001','11110'],
'E':['11111','10000','10000','11110','10000','10000','11111'],
'F':['11111','10000','10000','11110','10000','10000','10000'],
'G':['01111','10000','10000','10111','10001','10001','01111'],
'H':['10001','10001','10001','11111','10001','10001','10001'],
'I':['11111','00100','00100','00100','00100','00100','11111'],
'J':['00111','00010','00010','00010','10010','10010','01100'],
'K':['10001','10010','10100','11000','10100','10010','10001'],
'L':['10000','10000','10000','10000','10000','10000','11111'],
'M':['10001','11011','10101','10101','10001','10001','10001'],
'N':['10001','11001','10101','10011','10001','10001','10001'],
'O':['01110','10001','10001','10001','10001','10001','01110'],
'P':['11110','10001','10001','11110','10000','10000','10000'],
'Q':['01110','10001','10001','10001','10101','10010','01101'],
'R':['11110','10001','10001','11110','10100','10010','10001'],
'S':['01111','10000','10000','01110','00001','00001','11110'],
'T':['11111','00100','00100','00100','00100','00100','00100'],
'U':['10001','10001','10001','10001','10001','10001','01110'],
'V':['10001','10001','10001','10001','10001','01010','00100'],
'W':['10001','10001','10001','10101','10101','10101','01010'],
'X':['10001','10001','01010','00100','01010','10001','10001'],
'Y':['10001','10001','01010','00100','00100','00100','00100'],
'Z':['11111','00001','00010','00100','01000','10000','11111'],
'0':['01110','10011','10101','10101','11001','10001','01110'],
'1':['00100','01100','00100','00100','00100','00100','01110'],
'2':['01110','10001','00001','00110','01000','10000','11111'],
'3':['11110','00001','00001','01110','00001','00001','11110'],
'4':['00010','00110','01010','10010','11111','00010','00010'],
'5':['11111','10000','10000','11110','00001','00001','11110'],
'6':['01110','10000','10000','11110','10001','10001','01110'],
'7':['11111','00001','00010','00100','01000','01000','01000'],
'8':['01110','10001','10001','01110','10001','10001','01110'],
'9':['01110','10001','10001','01111','00001','00001','01110'],
'-':['00000','00000','00000','11111','00000','00000','00000'],
'.':['00000','00000','00000','00000','00000','00110','00110'],
'/':['00001','00001','00010','00100','01000','10000','10000'],
'+':['00000','00100','00100','11111','00100','00100','00000'],
' ':['00000'] * 7,
'?':['01110','10001','00001','00010','00100','00000','00100'],
}


def _text(name):
    import unicodedata
    try:
        value = name.decode('utf-8') if isinstance(name, bytes) else name
    except Exception:
        value = str(name)
    value = value.replace(u'Ł', 'L').replace(u'ł', 'l')
    value = u''.join(ch for ch in unicodedata.normalize('NFKD', value) if not unicodedata.combining(ch))
    return u''.join(ch if ch in GLYPHS else '?' for ch in value.upper())


def _rows(name):
    import re
    value = name
    if not isinstance(value, type(u'')):
        try: value = value.decode('utf-8')
        except Exception: value = str(value)
    value = re.sub(r'\[[^\]]{1,40}\]', '', value).strip()
    value = _text(value)
    words = value.split()
    rows = []
    current = ''
    for word in words:
        while len(word) > 18:
            if current:
                rows.append(current); current = ''
            rows.append(word[:18]); word = word[18:]
        if len(current) + len(word) + (1 if current else 0) <= 18:
            current = (current + ' ' + word).strip()
        else:
            if current: rows.append(current)
            current = word
    if current: rows.append(current)
    if not rows: rows = ['IPTV']
    if len(rows) > 3:
        rows = rows[:3]; rows[-1] = rows[-1][:17] + '.'
    return rows


def _chunk(tag, data):
    data = data if isinstance(data, bytes) else data.encode('ascii')
    return struct.pack('!I', len(data)) + tag + data + struct.pack('!I', zlib.crc32(tag + data) & 0xffffffff)


def create_placeholder(name, width=240, height=140):
    """Return a bounded PNG; visibly marked as a generated IPTV fallback."""
    width, height = int(width), int(height)
    if width != 240 or height != 140:
        raise ValueError('Unsupported canvas size')
    background = (14, 27, 43)
    accent = (0, 174, 201)
    ink = (245, 250, 251)
    data = bytearray(background * (width * height))
    def rect(x, y, w, h, rgb):
        for yy in range(max(0,y), min(height,y+h)):
            for xx in range(max(0,x), min(width,x+w)):
                start = (yy*width+xx)*3
                data[start:start+3] = bytearray(rgb)
    rect(0, 0, width, 5, accent)
    rect(0, height-5, width, 5, accent)
    lines = _rows(name)
    scale = 2 if max(len(row) for row in lines) > 13 else 3
    line_h = 7*scale + 11
    y0 = max(15, (height-len(lines)*line_h)//2 + 5)
    for index, line in enumerate(lines):
        x = max(5, (width - (len(line)*6-1)*scale)//2)
        y = y0 + index*line_h
        for char in line:
            for ry, glyph in enumerate(GLYPHS.get(char, GLYPHS['?'])):
                for rx, bit in enumerate(glyph):
                    if bit == '1': rect(x+rx*scale,y+ry*scale,scale,scale,ink)
            x += 6*scale
    # Bottom right marker distinguishes fallback from genuine brand icon.
    rect(width-20, height-19, 8, 8, accent)
    rows = b''.join(b'\x00' + data[y*width*3:(y+1)*width*3].decode('latin1').encode('latin1') for y in range(height))
    return b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', struct.pack('!2I5B', width,height,8,2,0,0,0)) + _chunk(b'tEXt', b'SimpleIPTVEPG\x00Generated fallback v1') + _chunk(b'IDAT', zlib.compress(rows, 7)) + _chunk(b'IEND',b'')
