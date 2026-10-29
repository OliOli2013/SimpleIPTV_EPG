# -*- coding: utf-8 -*-
"""Conservative IPTV EPG mapping guard (Python 2.7/3.x).
Only the in-memory IPTV target list and XMLTV mapping are inspected.
No bouquet, SAT data, epg.dat or existing picon file is ever modified.
"""
from __future__ import absolute_import

import gzip
import os
import re
import unicodedata
import xml.etree.ElementTree as ET

try:
    text_type = unicode
except NameError:
    text_type = str

TECH = set(['HD','FHD','FULLHD','UHD','4K','SD','HEVC','H265','H264','1080P','720P',
            '576P','IPTV','STREAM','LIVE','OTT','HLS','YT','YOUTUBE'])
GENERIC = set(['TV','RADIO','CHANNEL','KANAL'])


def _text(value):
    if value is None:
        return u''
    if isinstance(value, text_type):
        return value
    try:
        return value.decode('utf-8', 'ignore')
    except Exception:
        return text_type(value)


def _norm(name):
    value = _text(name).strip().upper()
    value = re.sub(r'^\s*[A-Z]{2}:\s*', ' ', value)
    value = re.sub(r'\[(?:[A-Z]{2,3}(?:/[A-Z]{2,3})?|[A-Z]{2,3}_[A-Z0-9_]+)\]', ' ', value)
    value = re.sub(r'\((?:YT|YOUTUBE|HD|FHD|UHD|4K|HLS|IPTV)\)', ' ', value)
    value = value.replace('CANAL+', 'CANAL PLUS').replace('C+', 'CANAL PLUS')
    value = re.sub(r'\.PL\b', '', value)  # domain suffix, not channel variant
    value = value.replace(u'Ł', 'L')
    value = u''.join(ch for ch in unicodedata.normalize('NFKD', value) if not unicodedata.combining(ch))
    value = re.sub(r'[^\w]+', ' ', value, flags=re.UNICODE)
    tokens = tuple(word for word in value.split() if word not in TECH)
    return tokens


# Suffixes that identify a DIFFERENT service, not just the picture quality.
# These must never be added through an unrelated XMLTV alias.
DISTINCT = set(['PREMIERA', 'PREMIUM', 'EXTRA', 'LIVE', 'SPORT', 'NEWS',
                'JUNIOR', 'KIDS', 'HITS', 'CLASSIC', 'INTERNATIONAL',
                'HISTORIA', 'HISTORY', 'DANCE', 'MAX', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10'])


def _match_names(service_name, xml_names):
    target = _norm(service_name)
    if not target or all(token in GENERIC for token in target):
        return False
    compact = u''.join(target)
    if len(compact) < 4:
        return False
    primary = _norm(xml_names[0]) if xml_names else ()
    # A provider may group many different channels under one XMLTV entry and
    # put their names into aliases (e.g. RakutenTV -> Qwest TV). An alias alone
    # is NOT evidence of identical programmes. Require primary-name agreement,
    # allowing only cosmetic TV / CHANNEL / KANAL differences.
    if primary:
        primary_core = sorted(word for word in primary if word not in GENERIC)
        target_core = sorted(word for word in target if word not in GENERIC)
        if u''.join(primary) != compact and u''.join(primary_core) != u''.join(target_core):
            return False
    target_sorted = sorted(target)
    for alias in xml_names:
        parts = _norm(alias)
        if not parts or all(token in GENERIC for token in parts):
            continue
        if u''.join(parts) == compact:
            return True
        if len(parts) > 1 and len(target) > 1 and sorted(parts) == target_sorted:
            return True
    return False


def _xml_names(xml_path, keys):
    names = {}
    if not keys or not os.path.isfile(xml_path):
        return names
    opener = gzip.open if xml_path.lower().endswith('.gz') else open
    with opener(xml_path, 'rb') as handle:
        for _event, elem in ET.iterparse(handle, events=('end',)):
            kind = elem.tag.rsplit('}', 1)[-1].lower()
            if kind == 'channel':
                cid = _text(elem.get('id'))
                if cid in keys:
                    names[cid] = [_text(x.text) for x in elem if x.tag.rsplit('}', 1)[-1].lower() == 'display-name' and x.text]
                    # IDs such as TVP1.pl are useful; pure numeric IDs are not names.
                    if not cid.isdigit():
                        names[cid].append(cid)
                elem.clear()
            elif kind == 'programme':
                # Valid XMLTV normally declares channels before programmes.
                break
    return names


def _identity(ref):
    parts = _text(ref).split(':', 10)
    if len(parts) < 11:
        return None
    try:
        return tuple(int(parts[index], 16) for index in (3, 4, 5, 6))
    except (TypeError, ValueError):
        return None


def filter_unsafe_refs(services):
    """Exclude zero DVB identities and aliases colliding across distinct channel names."""
    groups = {}
    for entry in services:
        ref = entry.get('full_ref', '')
        key = _identity(ref)
        if key and any(key):
            groups.setdefault(key, set()).add(u''.join(_norm(entry.get('name', ''))))
    output = []
    stats = {'zero_or_invalid': 0, 'colliding_names': 0, 'pseudoref': 0}
    for entry in services:
        ref = entry.get('full_ref', '')
        if _text(ref).startswith('1:64:'):
            stats['pseudoref'] += 1
            continue
        key = _identity(ref)
        if not key or not any(key):
            stats['zero_or_invalid'] += 1
        elif len(groups.get(key, ())) > 1:
            stats['colliding_names'] += 1
        else:
            output.append(entry)
    return output, stats


def guard_mapping(mapping, services, xml_path, overrides=None):
    """Keep only XMLTV matches provably consistent with IPTV display names.
    False negatives are safer than injecting a different station's EPG.
    """
    by_ref = dict((item.get('full_ref'), item.get('name', '')) for item in services if item.get('full_ref'))
    overrides = overrides or {}
    allowed_names = _xml_names(xml_path, set(mapping or {}))
    result = {}
    stats = {'accepted_refs': 0, 'rejected_refs': 0, 'rejected_ids': 0}
    for cid, refs in (mapping or {}).items():
        seen = set()
        for ref in refs:
            if ref in seen:
                continue
            seen.add(ref)
            name = by_ref.get(ref)
            explicit = bool(name and (overrides.get(name) == cid or overrides.get(u''.join(_norm(name))) == cid))
            if not name or not (explicit or _match_names(name, allowed_names.get(cid, []))):
                stats['rejected_refs'] += 1
                continue
            result.setdefault(cid, []).append(ref)
            stats['accepted_refs'] += 1
        if cid not in result:
            stats['rejected_ids'] += 1
    return result, stats
