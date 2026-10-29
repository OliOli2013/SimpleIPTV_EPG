# -*- coding: utf-8 -*-
"""IPTV-only picon completer. Never edits SAT references or existing logos.

Python 2.7 / Python 3 compatible, stdlib-first. PNG input can be copied
without external dependencies; JPEG/WebP/SVG conversion is optional.
"""
from __future__ import absolute_import, print_function

import io
import json
import os
import re
import shutil
import socket
import tempfile
import time
import xml.etree.ElementTree as ET

try:
    from urllib2 import HTTPRedirectHandler, Request, build_opener
    from urlparse import urlparse
except ImportError:
    from urllib.request import HTTPRedirectHandler, Request, build_opener
    from urllib.parse import urlparse

from .compat import command_exists, ensure_dir, run_command, to_text
from .epgcore import compact_name, local_tag, POLISH_MAP

CATALOG_CHANNELS = 'https://iptv-org.github.io/api/channels.json'
CATALOG_LOGOS = 'https://iptv-org.github.io/api/logos.json'
PNG_HEADER = b'\x89PNG\r\n\x1a\n'
MAX_ICON = 2 * 1024 * 1024
MAX_CATALOG = 14 * 1024 * 1024
MAX_LOGOS = 200
MAX_DOWNLOADS = 80                  # Protect flash; not a service cap for EPG.


def _private_address(addr):
    """Reject loopback, private, link-local, multicast, reserved IPv4/v6."""
    try:
        import ipaddress
        ip = ipaddress.ip_address(to_text(addr).split('%', 1)[0])
        return not ip.is_global
    except ImportError:
        pass
    except ValueError:
        return True
    if ':' in addr:  # IPv6 on Python2: require external resolver support.
        value = addr.lower()
        return value.startswith(('::1', 'fc', 'fd', 'fe8', 'fe9', 'fea', 'feb', 'ff', '::ffff:'))
    try:
        numbers = [int(x) for x in addr.split('.')]
        if len(numbers) != 4 or any(x < 0 or x > 255 for x in numbers):
            return True
        a, b = numbers[:2]
        return (a in (0, 10, 127) or a >= 224 or (a == 169 and b == 254)
                or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168)
                or (a == 100 and 64 <= b <= 127) or (a == 198 and b in (18, 19))
                or (a == 192 and b in (0, 2)) or (a == 198 and b == 51)
                or (a == 203 and b == 0) or (a == 192 and b == 88))
    except Exception:
        return True


def public_url(url):
    """No file/private-network URLs. Block DNS-resolved local addresses too."""
    try:
        value = to_text(url).strip()
        if len(value) > 2048:
            return False
        parsed = urlparse(value)
        if parsed.scheme.lower() not in ('https', 'http') or not parsed.hostname:
            return False
        if parsed.username or parsed.password:
            return False
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), 0, socket.SOCK_STREAM)
        return bool(infos) and all(not _private_address(item[4][0]) for item in infos)
    except Exception:
        return False


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch(url, maximum, timeout=15):
    if not public_url(url):
        return None
    response = None
    try:
        opener = build_opener(_NoRedirect())
        response = opener.open(Request(url, headers={'User-Agent': 'SimpleIPTVEPG/3.2', 'Accept': 'image/png,image/*;q=0.8,application/json;q=0.5'}), timeout=timeout)
        length = response.info().get('Content-Length')
        if length and int(length) > maximum:
            return None
        data = response.read(maximum + 1)
        return data if data and len(data) <= maximum else None
    except Exception:
        return None
    finally:
        if response:
            try:
                response.close()
            except Exception:
                pass


def _picon_dir():
    # Reuse an existing directory; do not create a new unmounted /media path.
    paths = ('/media/usb/picon', '/media/hdd/picon', '/usr/share/enigma2/picon', '/picon')
    for path in paths:
        if os.path.isdir(path) and os.access(path, os.W_OK):
            return path
    target = '/usr/share/enigma2/picon'
    try:
        ensure_dir(target)
        return target if os.access(target, os.W_OK) else None
    except Exception:
        return None


def _snp(name):
    value = to_text(name).lower()
    for key, replacement in POLISH_MAP.items():
        value = value.replace(key.lower(), replacement.lower())
    value = value.replace('canal+', 'canalplus').replace('c+', 'canalplus')
    return re.sub('[^a-z0-9]', '', value)


def _srp(ref):
    fields = to_text(ref).split(':', 10)
    if len(fields) != 11 or not fields[0].isdigit():
        return None
    if not all(re.match('^[0-9A-Fa-f]+$', x or '') for x in fields[1:10]):
        return None
    # All-zero IPTV tuple is shared by many channels: picon would be wrong.
    if not any(x.strip('0') for x in fields[3:7]):
        return None
    return '_'.join(fields[:10]).upper() + '.png'


def _normalized_image_bytes(blob):
    if blob and blob.startswith(PNG_HEADER):
        return blob
    if not blob:
        return None
    try:
        from PIL import Image
        image = Image.open(io.BytesIO(blob))
        image.thumbnail((400, 240))
        out = io.BytesIO()
        image.convert('RGBA').save(out, 'PNG')
        return out.getvalue()
    except Exception:
        pass
    converter = command_exists('convert') or command_exists('magick')
    if not converter:
        return None
    tempin = tempfile.NamedTemporaryFile(prefix='simpleepg_icon_', suffix='.bin', delete=False)
    output = tempin.name + '.png'
    try:
        tempin.write(blob)
        tempin.close()
        code, _result = run_command([converter, tempin.name, '-resize', '400x240>', 'png:' + output], timeout=12)
        if code == 0 and os.path.exists(output) and os.path.getsize(output) <= MAX_ICON:
            with open(output, 'rb') as handle:
                result = handle.read(MAX_ICON + 1)
                return result if result.startswith(PNG_HEADER) else None
    except Exception:
        pass
    finally:
        try:
            os.unlink(tempin.name)
        except Exception:
            pass
        try:
            os.unlink(output)
        except Exception:
            pass
    return None


def _write_new_png(destination, blob):
    """Exclusive creation: never alter an existing SAT / user picon."""
    if not blob or not blob.startswith(PNG_HEADER) or os.path.lexists(destination):
        return False
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        try:
            with os.fdopen(descriptor, 'wb') as target:
                target.write(blob)
        except Exception:
            try:
                os.unlink(destination)
            except Exception:
                pass
            raise
        return True
    except (IOError, OSError):
        return False


def _icon_map(xml_path, selected_ids):
    result = {}
    if not xml_path or not os.path.isfile(xml_path) or not selected_ids:
        return result
    import gzip
    opener = gzip.open if xml_path.lower().endswith('.gz') else open
    try:
        with opener(xml_path, 'rb') as handle:
            root = None
            channel_seen = False
            for kind, elem in ET.iterparse(handle, events=('start', 'end')):
                if root is None and kind == 'start':
                    root = elem
                if kind != 'end':
                    continue
                tag = local_tag(elem.tag)
                if tag == 'channel':
                    channel_seen = True
                    ident = elem.get('id')
                    if ident in selected_ids:
                        for child in elem:
                            if local_tag(child.tag) == 'icon':
                                url = to_text(child.get('src') or '')
                                if url:
                                    result[ident] = url
                                    break
                    elem.clear()
                elif tag == 'programme':
                    # Normal XMLTV lists channels before millions of programmes.
                    if channel_seen:
                        break
                    elem.clear()
                    if root is not None:
                        root.clear()
    except (ET.ParseError, IOError, OSError):
        return result
    return result


def _catalog_index(names, ids):
    """Download official iptv-org metadata only when a local icon is absent.

    Avoid retaining whole catalogues on the receiver. No stream URLs or
    provider credentials are ever sent to the catalogue API.
    """
    raw_channels = _fetch(CATALOG_CHANNELS, MAX_CATALOG, 20)
    raw_logos = _fetch(CATALOG_LOGOS, MAX_CATALOG, 20)
    if not raw_channels or not raw_logos:
        return {}, {}
    channel_names = {}
    selected = set()
    try:
        for entry in json.loads(raw_channels.decode('utf-8')):
            cid = to_text(entry.get('id'))
            variants = [entry.get('name')] + (entry.get('alt_names') or [])
            if cid in ids or any(compact_name(v) in names for v in variants if v):
                selected.add(cid)
                for variant in variants:
                    key = compact_name(variant)
                    if key in names:
                        channel_names.setdefault(key, set()).add(cid)
        candidates = {}
        for logo in json.loads(raw_logos.decode('utf-8')):
            cid = to_text(logo.get('channel'))
            if cid not in selected:
                continue
            value = to_text(logo.get('url'))
            # Prefer current PNG logos, then legacy PNG; optional converters for others.
            score = (4 if logo.get('in_use') else 0) + (2 if logo.get('format') == 'PNG' else 0) + (1 if logo.get('feed') is None else 0)
            current = candidates.get(cid)
            if value and (current is None or score > current[0]):
                candidates[cid] = (score, value)
        return channel_names, dict((cid, data[1]) for cid, data in candidates.items())
    except (ValueError, TypeError, AttributeError):
        return {}, {}


def install_picons(services, mappings, sat_services=None, allow_catalog=True, log_cb=None, max_new=MAX_LOGOS):
    """mappings: [(path_to_XMLTV, {xmltv_id: [full_iptv_refs]})].

    Only absent IPTV logos are created. SAT services/bouquets/EPG are untouched.
    Count 'created' as PNG files, 'covered' as distinct IPTV service refs.
    """
    directory = _picon_dir()
    stats = {'directory': directory or '', 'created': 0, 'covered': 0, 'skipped': 0, 'catalog': 0, 'xmltv': 0, 'local_sat': 0}
    if not directory:
        return stats
    services = [entry for entry in services if entry.get('full_ref')]
    ref_to_ids = {}
    icon_by_ref = {}
    for xml_path, mapping in mappings:
        ids = set(mapping or {})
        images = _icon_map(xml_path, ids)
        for cid, refs in (mapping or {}).items():
            for ref in refs:
                ref_to_ids.setdefault(ref, set()).add(cid)
                if cid in images and ref not in icon_by_ref:
                    icon_by_ref[ref] = images[cid]
    # Avoid collisions between two services with identical legacy reference tuple.
    by_srp = {}
    by_snp = {}
    for entry in services:
        identity = compact_name(entry.get('name', ''))
        key = _srp(entry['full_ref'])
        if key:
            by_srp.setdefault(key, set()).add(identity)
        if _snp(entry.get('name', '')):
            by_snp.setdefault(_snp(entry.get('name', '')), set()).add(identity)
    local_sat = {}
    for entry in sat_services or []:
        key = compact_name(entry.get('name'))
        picon = _srp(entry.get('full_ref', ''))
        if key and picon:
            candidate = os.path.join(directory, picon)
            if os.path.isfile(candidate) and os.path.getsize(candidate) <= MAX_ICON:
                local_sat.setdefault(key, candidate)
    wanted_names = set(compact_name(x.get('name')) for x in services if x.get('name'))
    wanted_ids = set(y for x in ref_to_ids.values() for y in x)
    cat_names, cat_logos = ({}, {})
    # Reuse local files and XMLTV first. Skip online metadata if nothing is missing.
    requires_online = any(
        _snp(x.get('name', '')) and
        not os.path.lexists(os.path.join(directory, _snp(x.get('name', '')) + '.png')) and
        x.get('full_ref') not in icon_by_ref and
        compact_name(x.get('name')) not in local_sat
        for x in services
    )
    if allow_catalog and requires_online:
        cat_names, cat_logos = _catalog_index(wanted_names, wanted_ids)
    fetched = {}
    seen_ref = set()
    for entry in services:
        ref = entry['full_ref']
        name = entry.get('name') or ''
        key = compact_name(name)
        snp = _snp(name)
        rp = _srp(ref)
        targets = []
        if rp and len(by_srp.get(rp, ())) == 1:
            targets.append(rp)
        if snp and len(snp) >= 3 and len(by_snp.get(snp, ())) == 1:
            targets.append(snp + '.png')
        if not targets:
            stats['skipped'] += 1
            continue
        missing = [os.path.join(directory, target) for target in targets if not os.path.lexists(os.path.join(directory, target))]
        if not missing:
            stats['covered'] += 1
            continue
        blob = None
        origin = ''
        if key in local_sat:
            try:
                with open(local_sat[key], 'rb') as reader:
                    blob = reader.read(MAX_ICON + 1)
                if not blob.startswith(PNG_HEADER):
                    blob = None
                origin = 'local_sat'
            except Exception:
                blob = None
        if not blob:
            url = icon_by_ref.get(ref)
            if url:
                origin = 'xmltv'
            else:
                ids = sorted(ref_to_ids.get(ref, []))
                match = [cid for cid in ids if cid in cat_logos]
                if len(match) == 1:
                    url = cat_logos[match[0]]
                elif len(cat_names.get(key, set())) == 1:
                    url = cat_logos.get(next(iter(cat_names[key])))
                origin = 'catalog'
            if url:
                if url not in fetched:
                    # Explicit cap on remote fetches avoids blocking weaker boxes.
                    if len(fetched) >= MAX_DOWNLOADS:
                        fetched[url] = None
                    else:
                        fetched[url] = _normalized_image_bytes(_fetch(url, MAX_ICON))
                blob = fetched[url]
        if not blob:
            stats['skipped'] += 1
            continue
        created = 0
        for target in missing:
            if stats['created'] >= max_new:
                break
            if _write_new_png(target, blob):
                created += 1
                stats['created'] += 1
        if created:
            stats['covered'] += 1
            stats[origin] += 1
            seen_ref.add(ref)
    if log_cb:
        log_cb('Picony IPTV: %s nowych plików, %s usług z logiem, %s bez źródła. Katalog: %s' % (
            stats['created'], stats['covered'], stats['skipped'], directory))
    return stats
