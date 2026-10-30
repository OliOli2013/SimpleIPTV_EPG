# -*- coding: utf-8 -*-
"""Small, deterministic EPG source planner and reference de-duplicator.

Only plans country-specific XMLTV URLs. Never modifies bouquets, eEPGCache or
satellite references. Supports both Python 2 and Python 3 on Enigma2.
"""
from __future__ import absolute_import, print_function

import re
from collections import Counter
from .epgcore import compact_name


REGIONAL_EPG = {
    'US': 'US2', 'UK': 'UK1', 'DE': 'DE1', 'FR': 'FR1', 'IT': 'IT1',
    'ES': 'ES1', 'CZ': 'CZ1', 'SK': 'SK1', 'NL': 'NL1', 'CA': 'CA1',
    'AU': 'AU1', 'IN': 'IN1', 'UA': 'UA1', 'SE': 'SE1', 'HU': 'HU1',
    'PT': 'PT1', 'TR': 'TR1', 'BE': 'BE1',
}
# iptv-epg.org publishes a separate country XMLTV for several regions
# not present in the short EPGShare selection (no credentials needed).
ALTERNATE_COUNTRY_URLS = {
    'RU': 'https://iptv-epg.org/files/epg-ru.xml.gz',
    'RO': 'https://iptv-epg.org/files/epg-ro.xml.gz',
    'BY': 'https://iptv-epg.org/files/epg-by.xml.gz',
    'AT': 'https://iptv-epg.org/files/epg-at.xml.gz',
    'HR': 'https://iptv-epg.org/files/epg-hr.xml.gz',
    'BG': 'https://iptv-epg.org/files/epg-bg.xml.gz',
    'RS': 'https://iptv-epg.org/files/epg-rs.xml.gz',
    'GR': 'https://iptv-epg.org/files/epg-gr.xml.gz',
    'CH': 'https://iptv-epg.org/files/epg-ch.xml.gz',
    'DK': 'https://iptv-epg.org/files/epg-dk.xml.gz',
    'FI': 'https://iptv-epg.org/files/epg-fi.xml.gz',
    'NO': 'https://iptv-epg.org/files/epg-no.xml.gz',
}
COUNTRY_ALIASES = {
    'GB': 'UK', 'GBR': 'UK', 'USA': 'US', 'DEU': 'DE', 'GER': 'DE',
    'FRA': 'FR', 'ITA': 'IT', 'ESP': 'ES', 'CZE': 'CZ', 'SVK': 'SK',
    'NLD': 'NL', 'CAN': 'CA', 'AUS': 'AU', 'IND': 'IN', 'UKR': 'UA',
    'SWE': 'SE', 'POL': 'PL', 'RUS': 'RU', 'ROU': 'RO', 'HUN': 'HU',
    'AUT': 'AT', 'BEL': 'BE', 'TUR': 'TR', 'POR': 'PT',
    'HRV': 'HR', 'BGR': 'BG', 'SRB': 'RS', 'GRC': 'GR',
    'CHE': 'CH', 'DNK': 'DK', 'FIN': 'FI', 'NOR': 'NO',
}
COUNTRY_RE = re.compile(r'\[([^\]]+)\]')
PREFIX_RE = re.compile(r'^\s*([A-Z]{2,3})\s*[:|]\s+', re.I)
HEX_RE = re.compile(r'^[0-9a-fA-F]+$')
VALID_COUNTRIES = set(REGIONAL_EPG) | set(ALTERNATE_COUNTRY_URLS)


def country_codes_from_name(name):
    """Read explicit [USA/CA], [HU/RO/CZ/SK] or 'DE: ...' tags only.

    Never guess a country from an untagged name or the language of the title.
    """
    text = name or ''
    groups = COUNTRY_RE.findall(text)
    result = []
    for group in groups:
        for token in re.split(r'[/,|+\s]+', group.upper()):
            code = COUNTRY_ALIASES.get(token, token)
            if code in VALID_COUNTRIES and code not in result:
                result.append(code)
    if not result:
        prefix = PREFIX_RE.match(text)
        if prefix:
            code = COUNTRY_ALIASES.get(prefix.group(1).upper(), prefix.group(1).upper())
            if code in VALID_COUNTRIES:
                result.append(code)
    return tuple(result)


def country_from_name(name):
    codes = country_codes_from_name(name)
    return codes[0] if codes else ''


def country_feed_url(code):
    if code in ALTERNATE_COUNTRY_URLS:
        return ALTERNATE_COUNTRY_URLS[code]
    if code in REGIONAL_EPG:
        return 'https://epgshare01.online/epgshare01/epg_ripper_%s.xml.gz' % REGIONAL_EPG[code]
    return ''


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


def country_assignments(services):
    """Tag-only country inference + exact-title inherit for ALT duplicates.

    Untagged standalone channels are never guessed by language or provider URL.
    Unambiguous tagged peer with exactly the same canonical name is required.
    """
    peers = {}
    for service in services:
        name = service.get('name', '')
        tags = country_codes_from_name(name)
        key = compact_name(name)
        if key and tags:
            peers.setdefault(key, set()).add(tags)
    inherited = dict((key, next(iter(options))) for key, options in peers.items()
                     if len(options) == 1)
    result = {}
    for service in services:
        ref = service.get('full_ref', '')
        tags = country_codes_from_name(service.get('name', ''))
        if not tags:
            tags = inherited.get(compact_name(service.get('name', '')), ())
        result[ref] = tags
    return result


def choose_country_feeds(services, used_urls=(), limit=4, minimum=2):
    """Select a few regional feeds for uncovered tagged channels, even small bouquets.

    The function does not make requests, and cannot infer region for untagged
    channels. A chosen feed is a candidate, not a guarantee of EPG coverage.
    """
    counts = Counter()
    assignments = country_assignments(services)
    seen = set()
    for service in services:
        ref = service.get('full_ref', '')
        key = reference_fingerprint(ref)
        if key in seen:
            continue
        seen.add(key)
        for code in (service.get('country_tags') or assignments.get(ref, ())):
            counts[code] += 1
    already = set(used_urls or ())
    chosen = []
    # Deterministic selection with a conservative cap for slow receivers.
    for code, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        if count < minimum:
            continue
        url = country_feed_url(code)
        if url and url not in already:
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
