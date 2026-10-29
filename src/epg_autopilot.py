# -*- coding: utf-8 -*-
"""Small, deterministic EPG source planner and reference de-duplicator.

Only plans country-specific XMLTV URLs. Never modifies bouquets, eEPGCache or
satellite references. Supports both Python 2 and Python 3 on Enigma2.
"""
from __future__ import absolute_import, print_function

import re
from collections import Counter


REGIONAL_EPG = {
    'US': 'US2', 'UK': 'UK1', 'DE': 'DE1', 'FR': 'FR1', 'IT': 'IT1',
    'ES': 'ES1', 'CZ': 'CZ1', 'SK': 'SK1', 'NL': 'NL1', 'CA': 'CA1',
    'AU': 'AU1', 'IN': 'IN1', 'UA': 'UA1', 'SE': 'SE1', 'HU': 'HU1',
    'PT': 'PT1', 'TR': 'TR1', 'BE': 'BE1',
}
COUNTRY_ALIASES = {'GB': 'UK', 'USA': 'US', 'GBR': 'UK', 'DEU': 'DE',
                   'FRA': 'FR', 'ITA': 'IT', 'ESP': 'ES', 'CZE': 'CZ',
                   'SVK': 'SK', 'NLD': 'NL', 'CAN': 'CA', 'AUS': 'AU',
                   'IND': 'IN', 'UKR': 'UA', 'SWE': 'SE'}
COUNTRY_RE = re.compile(r'\[([A-Z]{2,3})\]\s*$', re.I)
HEX_RE = re.compile(r'^[0-9a-fA-F]+$')


def country_from_name(name):
    result = COUNTRY_RE.search(name or '')
    if result is None:
        return ''
    code = result.group(1).upper()
    return COUNTRY_ALIASES.get(code, code)


def reference_fingerprint(reference):
    """Treat only hexadecimal-case differences in the Enigma2 header as duplicates.

    Do not lowercase the URL: its path, parameters and credentials are case-sensitive.
    Do not deduplicate streams merely because their DVB IDs are equal.
    """
    parts = (reference or '').split(':', 10)
    if len(parts) != 11:
        return reference
    header = []
    for part in parts[:10]:
        if not part or not HEX_RE.match(part):
            return reference
        header.append('%X' % int(part, 16))
    return ':'.join(header) + ':' + parts[10]


def dedupe_mapping(mapping):
    clean = {}
    removed = 0
    for guide_id, refs in (mapping or {}).items():
        seen = set()
        deduped = []
        for ref in refs or []:
            marker = reference_fingerprint(ref)
            if marker in seen:
                removed += 1
                continue
            seen.add(marker)
            deduped.append(ref)
        if deduped:
            clean[guide_id] = deduped
    return clean, removed


def choose_country_feeds(services, used_urls=(), limit=2, minimum=12):
    """Choose limited foreign XMLTV backups only when enough IPTV names have tags.

    The function does not make requests, and cannot infer region for untagged
    channels. A chosen feed is a candidate, not a guarantee of EPG coverage.
    """
    counts = Counter()
    seen = set()
    for service in services:
        ref = service.get('full_ref', '')
        key = reference_fingerprint(ref)
        if key in seen:
            continue
        seen.add(key)
        code = country_from_name(service.get('name', ''))
        if code in REGIONAL_EPG:
            counts[code] += 1
    already = set(used_urls or ())
    chosen = []
    # Deterministic selection with a conservative cap for slow receivers.
    for code, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        if count < minimum:
            continue
        url = 'https://epgshare01.online/epgshare01/epg_ripper_%s.xml.gz' % REGIONAL_EPG[code]
        if url not in already:
            chosen.append((code, url, count))
        if len(chosen) >= max(0, int(limit)):
            break
    return chosen


def likely_unscheduled_count(services):
    """Diagnostic estimate only; never automatically exclude these services."""
    needles = ('kamera', 'webcam', 'widok na', 'rynek', 'ulica', 'stok',
               'parking', 'live cam', 'radio ', ' fm ', '  (yt)', ' [yt]')
    total = 0
    for service in services:
        name = (' ' + (service.get('name', '') or '').lower() + ' ')
        if any(word in name for word in needles):
            total += 1
    return total
