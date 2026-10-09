# -*- coding: utf-8 -*-
"""Read BouquetMakerXtream/EPGImport source and channel links, without modifying them.

All refs are resolved to the ACTUAL IPTV bouquet service references. We never
rewrite bouquet files or EPGImport configuration, avoiding interference with BMX.
"""
from __future__ import absolute_import

import hashlib
import os
import xml.etree.ElementTree as ET

from .compat import to_bytes, to_text

EPG_DIR = '/etc/epgimport'


def _tag(name):
    return to_text(name).rsplit('}', 1)[-1].lower()


def safe_url(url):
    """Do not expose Xtream credentials in screens, files or runtime logs."""
    from .compat import urlparse
    value = to_text(url)
    try:
        p = urlparse(value)
        hostname = p.hostname or ''
        port = (':%s' % p.port) if p.port else ''
        suffix = p.path.split('/')[-1]
        return '%s://%s%s/.../%s' % (p.scheme, hostname, port, suffix[:35])
    except Exception:
        return '[URL]'


def _inside(base, relative):
    if not relative or '://' in relative:
        return None
    base = os.path.realpath(base)
    path = os.path.realpath(os.path.join(base, relative))
    if path.startswith(base + os.sep) and os.path.isfile(path):
        return path
    return None


def discover_bmx_sources(base=EPG_DIR):
    """Return XMLTV URLs and their original *.channels.xml mappings."""
    found, keys = [], set()
    try:
        files = sorted(os.listdir(base))
    except OSError:
        return []
    for fname in files:
        low = fname.lower()
        if not low.startswith('bouquetmakerxtream') or not low.endswith('.sources.xml'):
            continue
        try:
            root = ET.parse(os.path.join(base, fname)).getroot()
            for source in root.iter():
                if _tag(source.tag) != 'source' or source.get('type', 'gen_xmltv') not in ('gen_xmltv', 'xmltv'):
                    continue
                rel = source.get('channels') or ''
                channels = _inside(base, rel)
                if not channels:
                    continue
                desc = ''
                urls = []
                for child in source:
                    key = _tag(child.tag)
                    if key == 'description':
                        desc = to_text(child.text).strip()
                    if key == 'url':
                        url = to_text(child.text).strip()
                        if url.startswith(('http://', 'https://')):
                            urls.append(url)
                for url in urls:
                    if (url, channels) in keys:
                        continue
                    keys.add((url, channels))
                    found.append({'id': 'BMX_AUTO', 'url': url, 'channels': channels,
                                  'description': desc or 'BouquetMakerXtream'})
        except (ET.ParseError, OSError, ValueError):
            continue
    return found


def _ref_path(ref):
    """Strip ONLY the optional display name, not the provider URL path."""
    text = to_text(ref).strip()
    parts = text.split(':', 10)
    if len(parts) != 11:
        return text
    tail = parts[10]
    if ':' in tail:
        stream, display = tail.rsplit(':', 1)
        if display and '/' not in display and '?' not in display and '#' not in display:
            tail = stream
    return ':'.join(parts[:10]) + ':' + tail


def _variants(ref):
    clean = _ref_path(ref)
    pieces = clean.split(':', 10)
    if len(pieces) < 11:
        return clean, '', ''
    # Same stream, different playback engine (4097 vs 5001 vs 1).
    engine_neutral = ':'.join(pieces[1:])
    # EPGImport mappings sometimes omit the stream URL. DVB identity only
    # allowed when genuinely unique in a bouquet, never for all-zero IDs.
    dvb = ':'.join(pieces[2:10])
    if not any(part.strip('0') for part in pieces[3:7]):
        dvb = ''
    return clean, engine_neutral, dvb


def _ref_index(iptv):
    direct, neutral, dvb = {}, {}, {}
    for service in iptv:
        ref = service.get('full_ref', '')
        if not ref:
            continue
        a, b, c = _variants(ref)
        direct.setdefault(a, set()).add(ref)
        if b:
            neutral.setdefault(b, set()).add(ref)
        if c:
            dvb.setdefault(c, set()).add(ref)
    return direct, neutral, dvb


def import_bmx_mapping(path, iptv):
    """ID -> original bouquet refs; avoids EPG bound to an unplayable surrogate."""
    if not path or not os.path.isfile(path):
        return {}, {'bmx_channels': 0, 'bmx_matches': 0, 'bmx_unmatched': 0}
    direct, neutral, dvb = _ref_index(iptv)
    result = {}
    scanned, matched, missed = 0, 0, 0
    context = ET.iterparse(path, events=('end',))
    for event, elem in context:
        if _tag(elem.tag) != 'channel':
            continue
        xml_id = to_text(elem.get('id')).strip()
        ref = to_text(elem.text).strip()
        if xml_id and ref:
            scanned += 1
            a, b, c = _variants(ref)
            refs = direct.get(a) or neutral.get(b)
            if not refs and c and len(dvb.get(c, [])) == 1:
                refs = dvb[c]
            if refs:
                matched += 1
                dest = result.setdefault(xml_id, [])
                for value in sorted(refs):
                    if value not in dest:
                        dest.append(value)
            else:
                missed += 1
        elem.clear()
    return result, {'bmx_channels': scanned, 'bmx_matches': matched, 'bmx_unmatched': missed}


def channels_signature(path):
    if not path or not os.path.isfile(path):
        return ''
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()[:20]


def combine_maps(native, fallback):
    """Native map has precedence; fuzzy cannot steal a service assigned by BMX."""
    merged = dict((k, list(v)) for k, v in native.items())
    used = set(ref for refs in native.values() for ref in refs)
    for xml_id, refs in fallback.items():
        selected = [ref for ref in refs if ref not in used]
        if selected:
            bucket = merged.setdefault(xml_id, [])
            for ref in selected:
                if ref not in bucket:
                    bucket.append(ref)
    return merged
