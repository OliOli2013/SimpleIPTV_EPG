# -*- coding: utf-8 -*-
"""Recognise and optionally delete ONLY PNG placeholders made by Simple IPTV EPG RC8.

Do not touch user picons, satellite logos, links or files lacking our exact PNG
metadata marker. No Enigma2 imports: can be tested independently on Linux.
"""
from __future__ import absolute_import
import os
import struct

PNG = b"\x89PNG\r\n\x1a\n"
MARKER = b"SimpleIPTVEPG\x00Generated fallback v1"


def is_generated_picon(path):
    try:
        if not path.lower().endswith('.png') or os.path.islink(path) or not os.path.isfile(path):
            return False
        with open(path, 'rb') as handle:
            if handle.read(8) != PNG:
                return False
            header_ok = False
            for number in range(12):
                chunk = handle.read(8)
                if len(chunk) != 8:
                    return False
                length, kind = struct.unpack('!I4s', chunk)
                if length > 4096:
                    return False
                data = handle.read(length)
                checksum = handle.read(4)
                if len(data) != length or len(checksum) != 4:
                    return False
                if kind == b'IHDR':
                    header_ok = length == 13 and struct.unpack('!II', data[:8]) == (240, 140)
                if kind == b'tEXt' and data == MARKER:
                    return bool(header_ok)
                if kind in (b'IDAT', b'IEND'):
                    return False
        return False
    except (IOError, OSError, ValueError, struct.error):
        return False


def cleanup_generated(directory, dry_run=True):
    """Only top-level existing regular PNGs, exact RC8 marker; deliberate opt-in."""
    result = dict(directory=directory or '', found=0, removed=0, errors=0)
    if not directory or not os.path.isdir(directory):
        return result
    for name in os.listdir(directory):
        if not name.lower().endswith('.png'):
            continue
        path = os.path.join(directory, name)
        if not is_generated_picon(path):
            continue
        result['found'] += 1
        if not dry_run:
            # Revalidate just before unlinking; no wildcard and no symlinks.
            if is_generated_picon(path):
                try:
                    os.unlink(path)
                    result['removed'] += 1
                except (IOError, OSError):
                    result['errors'] += 1
    return result
