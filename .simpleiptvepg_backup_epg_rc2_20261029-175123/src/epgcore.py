# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function

import calendar
import datetime
import difflib
import gzip
import hashlib
import os
import re
import shutil
import time
import xml.etree.ElementTree as ET

from .compat import (
    Request, command_exists, ensure_dir, io_open, run_command, to_bytes,
    to_text, unquote, urlopen,
)
from .constants import (
    LOG_FILE, MAPPING_FILE, OVERRIDES_FILE, PACKAGE_NAME, REMOTE_INSTALLER_URL,
    REMOTE_VERSION_URL, TMP_DIR,
)
from .logger import log_message
from .storage import atomic_write_json, load_json

POLISH_MAP = {
    u"Ą": "A", u"Ć": "C", u"Ę": "E", u"Ł": "L", u"Ń": "N", u"Ó": "O", u"Ś": "S", u"Ź": "Z", u"Ż": "Z",
    u"ą": "A", u"ć": "C", u"ę": "E", u"ł": "L", u"ń": "N", u"ó": "O", u"ś": "S", u"ź": "Z", u"ż": "Z",
}

NOISE_WORDS = set([
    "HD", "FHD", "FULLHD", "UHD", "4K", "HEVC", "H265", "H264", "SD", "PL", "POL", "POLSKA", "TV", "LIVE", "VIP",
    "BACKUP", "TEST", "RAW", "LEKTOR", "DUB", "SUB", "ORIGINAL", "OTV", "ORG", "MULTI", "KANAL", "EU", "EUROPE",
    "INTERNATIONAL", "INT", "CHANNEL", "OTT", "MPEGTS", "DASH", "HLS", "1080P", "720P", "576P", "50FPS", "60FPS",
    "X264", "X265", "AAC", "AC3", "EAC3", "DVB", "IPTV", "STREAM", "FEED", "PLUSX",
])

MANUAL_ALIASES = {
    "CANALPLUS": ["CANAL PLUS", "C+", "CANAL+"],
    "CANALPLUSDOCUMENT": ["CANAL+ DOKUMENT", "CANAL PLUS DOKUMENT"],
    "CANALPLUSFILM": ["CANAL+ FILM", "CANAL PLUS FILM"],
    "CANALPLUSSPORT": ["CANAL+ SPORT", "CANAL PLUS SPORT"],
    "TVP1": ["TVP 1"], "TVP2": ["TVP 2"], "TVP3": ["TVP 3"],
    "TVN7": ["TVN 7"], "TVN24": ["TVN 24"],
    "POLSAT2": ["POLSAT 2"], "POLSATNEWS2": ["POLSAT NEWS 2"],
    "ELEVENSPORTS1": ["ELEVEN SPORTS 1"], "ELEVENSPORTS2": ["ELEVEN SPORTS 2"],
    "ELEVENSPORTS3": ["ELEVEN SPORTS 3"], "ELEVENSPORTS4": ["ELEVEN SPORTS 4"],
    "EUROSPORT1": ["EUROSPORT 1"], "EUROSPORT2": ["EUROSPORT 2"],
    "HISTORY2": ["HISTORY 2", "H2"],
}


def local_tag(tag):
    value = to_text(tag)
    if "}" in value:
        value = value.rsplit("}", 1)[-1]
    if ":" in value:
        value = value.rsplit(":", 1)[-1]
    return value.lower()


def _replace_polish(value):
    for source, target in POLISH_MAP.items():
        value = value.replace(source, target)
    return value


def simplify_name(text):
    if text is None:
        return ""
    value = _replace_polish(to_text(text).upper())
    value = value.replace("CANAL+", "CANAL PLUS ").replace("C+", "CANAL PLUS ")
    value = value.replace("&", " AND ").replace("+", " PLUS ")
    value = value.replace("TVP1", "TVP 1 ").replace("TVP2", "TVP 2 ").replace("TVP3", "TVP 3 ")
    value = value.replace("TVN7", "TVN 7 ").replace("TVN24", "TVN 24 ")
    value = re.sub(r"\[[^\]]*\]", " ", value)
    value = re.sub(r"\([^\)]*\)", " ", value)
    value = re.sub(r"\bS0([1-9])\b", r"S\1", value)
    value = re.sub(r"\bE0([1-9])\b", r"E\1", value)
    value = re.sub(r"\.(?:[A-Z0-9]{1,4})\b", " ", value)
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    tokens = []
    for token in value.split():
        if token in NOISE_WORDS:
            continue
        if len(token) == 1 and not token.isdigit():
            continue
        if re.match(r"^(?:19|20)\d{2}$", token):
            continue
        tokens.append(token)
    return " ".join(tokens).strip()


def compact_name(text):
    return simplify_name(text).replace(" ", "")


def tokenize(text):
    return [token for token in simplify_name(text).split() if len(token) >= 2 or token.isdigit()]


def name_variants(text):
    base = simplify_name(text)
    compact = base.replace(" ", "")
    variants = set()
    if base:
        variants.add(base)
        variants.add(compact)
        variants.add(base.replace(" PLUS ", " "))
        variants.add(re.sub(r"\bTVP\s+(\d)\b", r"TVP\1", base))
        variants.add(re.sub(r"\bTVN\s+(\d+)\b", r"TVN\1", base))
        variants.add(base.replace(" TWO ", " 2 "))
        variants.add(base.replace(" ONE ", " 1 "))
    if compact in MANUAL_ALIASES:
        for item in MANUAL_ALIASES[compact]:
            variants.add(simplify_name(item))
            variants.add(compact_name(item))
    return [item for item in variants if item]


def extract_ref_hints(ref):
    if not ref:
        return []
    decoded = unquote(to_text(ref))
    hints = []
    patterns = [
        r"tvg-name=([^&:]+)", r"name=([^&:]+)", r"channel-name=([^&:]+)",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, decoded, flags=re.IGNORECASE):
            hints.append(match)
    return [to_text(item).strip() for item in hints if to_text(item).strip()]


def extract_xmltv_id_hints(ref):
    if not ref:
        return []
    decoded = unquote(to_text(ref))
    hints = []
    patterns = [
        r"tvg-id=([^&:]+)", r"epg_id=([^&:]+)", r"epgid=([^&:]+)",
        r"channel-id=([^&:]+)", r"xmltv=([^&:]+)", r"xmltv_id=([^&:]+)",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, decoded, flags=re.IGNORECASE):
            value = to_text(match).strip().strip('"\'')
            if value and value not in hints:
                hints.append(value)
    return hints


def is_iptv_ref(ref):
    lower = to_text(ref).lower()
    return (
        "4097:" in lower or "5001:" in lower or "5002:" in lower or "8193:" in lower
        or "http" in lower or "%3a" in lower or "rtmp" in lower or "rtsp" in lower
    )


def is_live_iptv(ref, name):
    lower_ref = to_text(ref).lower()
    upper_name = to_text(name).upper()
    for marker in ["/movie/", "/series/", "/vod/", "type=movie", "type=series", "catchup", "timeshift"]:
        if marker in lower_ref:
            return False
    for marker in [" VOD", "SERIALE", "SERIAL", "XXX VOD", "KINO VOD", "FILMY VOD", "MOVIES"]:
        if marker in upper_name:
            return False
    return True


def build_service_entry(ref, name):
    name = to_text(name).strip() or "IPTV"
    candidates = []
    seen = set()
    for raw in extract_ref_hints(ref) + [name]:
        for variant in name_variants(raw):
            compact = compact_name(variant)
            if compact and compact not in seen:
                seen.add(compact)
                candidates.append(compact)
    return {
        "full_ref": to_text(ref),
        "name": name,
        "norm": compact_name(name),
        "tokens": tokenize(name),
        "candidates": candidates,
        "id_hints": extract_xmltv_id_hints(ref),
    }


def _name_from_service_ref(ref):
    decoded = unquote(to_text(ref))
    if "http" in decoded.lower():
        # Most IPTV refs end in :<stream-url>:<display-name>. Do not treat URL tail as name.
        parts = decoded.rsplit(":", 1)
        if len(parts) == 2 and parts[1] and "/" not in parts[1] and "?" not in parts[1]:
            return parts[1].strip()
    return ""


def _scan_from_files():
    iptv = []
    sat_services = []
    skipped = 0
    seen = set()
    base = "/etc/enigma2"
    try:
        filenames = sorted([name for name in os.listdir(base) if name.startswith("userbouquet") and name.endswith(".tv")])
    except Exception:
        filenames = []
    for filename in filenames:
        path = os.path.join(base, filename)
        current_ref = None
        current_name = ""
        try:
            with io_open(path, "r") as handle:
                for raw_line in handle:
                    line = to_text(raw_line).strip()
                    if line.startswith("#SERVICE "):
                        if current_ref:
                            name = current_name or _name_from_service_ref(current_ref)
                            if current_ref not in seen and name and "###" not in name and "---" not in name:
                                seen.add(current_ref)
                                if is_iptv_ref(current_ref):
                                    if is_live_iptv(current_ref, name):
                                        iptv.append(build_service_entry(current_ref, name))
                                    else:
                                        skipped += 1
                                elif current_ref.startswith("1:0:"):
                                    sat_services.append(build_service_entry(current_ref, name))
                        current_ref = line[len("#SERVICE "):].strip()
                        current_name = ""
                    elif line.startswith("#DESCRIPTION") and current_ref:
                        current_name = line[len("#DESCRIPTION"):].strip()
                if current_ref:
                    name = current_name or _name_from_service_ref(current_ref)
                    if current_ref not in seen and name and "###" not in name and "---" not in name:
                        if is_iptv_ref(current_ref):
                            if is_live_iptv(current_ref, name):
                                iptv.append(build_service_entry(current_ref, name))
                            else:
                                skipped += 1
                        elif current_ref.startswith("1:0:"):
                            sat_services.append(build_service_entry(current_ref, name))
        except Exception as error:
            log_message("bouquet file scan error %s: %s" % (path, error))
    return iptv, sat_services, skipped


def _scan_from_memory():
    from enigma import eServiceCenter, eServiceReference
    iptv = []
    sat_services = []
    skipped = 0
    seen = set()
    service_center = eServiceCenter.getInstance()
    root = eServiceReference('1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.tv" ORDER BY bouquet')
    bouquets = service_center.list(root)
    if bouquets is None:
        return iptv, sat_services, skipped
    for bouquet_ref, _bouquet_name in (bouquets.getContent("SN") or []):
        bouquet_list = service_center.list(eServiceReference(bouquet_ref))
        if bouquet_list is None:
            continue
        for service_ref, service_name in (bouquet_list.getContent("SN") or []):
            ref = to_text(service_ref)
            name = to_text(service_name)
            if not ref or ref in seen or "###" in name or "---" in name:
                continue
            seen.add(ref)
            if is_iptv_ref(ref):
                if is_live_iptv(ref, name):
                    iptv.append(build_service_entry(ref, name))
                else:
                    skipped += 1
            elif ref.startswith("1:0:"):
                sat_services.append(build_service_entry(ref, name))
    return iptv, sat_services, skipped


def _merge(primary, secondary):
    out = []
    seen = set()
    for bucket in (primary or [], secondary or []):
        for item in bucket:
            ref = item.get("full_ref")
            if ref and ref not in seen:
                seen.add(ref)
                out.append(item)
    return out


def scan_bouquet_services(main_call=None):
    file_iptv, file_sat, file_skipped = _scan_from_files()
    mem_iptv, mem_sat, mem_skipped = [], [], 0
    try:
        if main_call:
            mem_iptv, mem_sat, mem_skipped = main_call(_scan_from_memory, timeout=30)
        else:
            mem_iptv, mem_sat, mem_skipped = _scan_from_memory()
    except Exception as error:
        log_message("memory bouquet scan unavailable: %s" % error)
    iptv = _merge(mem_iptv, file_iptv)
    sat_services = _merge(mem_sat, file_sat)
    digest = hashlib.sha256()
    for item in sorted(iptv, key=lambda entry: entry.get("full_ref", "")):
        digest.update(to_bytes(item.get("full_ref", "") + "|" + item.get("norm", "") + "\n"))
    sat_digest = hashlib.sha256()
    for item in sorted(sat_services, key=lambda entry: entry.get("full_ref", "")):
        sat_digest.update(to_bytes(item.get("full_ref", "") + "|" + item.get("norm", "") + "\n"))
    return {
        "iptv": iptv,
        "sat_services": sat_services,
        "skipped": int(file_skipped) + int(mem_skipped),
        "services_signature": digest.hexdigest() + ":" + sat_digest.hexdigest(),
    }


def source_fingerprint(url):
    return hashlib.sha256(to_bytes(url or "")).hexdigest()[:24]


def _download_with_urllib(url, target_path, timeout):
    request = Request(url, headers={"User-Agent": "SimpleIPTVEPG/3.0"})
    response = urlopen(request, timeout=timeout)
    try:
        with open(target_path, "wb") as handle:
            while True:
                chunk = response.read(128 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    finally:
        try:
            response.close()
        except Exception:
            pass
    return True


def download_file(url, target_path, timeout=180, retries=2, log_cb=None):
    ensure_dir(TMP_DIR)
    partial = target_path + ".part"
    for attempt in range(max(int(retries), 1)):
        try:
            if os.path.exists(partial):
                os.remove(partial)
        except Exception:
            pass
        ok = False
        try:
            curl = command_exists("curl")
            wget = command_exists("wget")
            if curl:
                code, output = run_command([
                    curl, "-fL", "--connect-timeout", "20", "--max-time", str(timeout),
                    "-A", "SimpleIPTVEPG/3.0", "-o", partial, url,
                ], timeout=timeout + 15)
                ok = code == 0
                if not ok:
                    log_message("curl download failed: %s" % output[-500:])
            if not ok and wget:
                code, output = run_command([
                    wget, "-q", "--timeout=%s" % timeout, "-O", partial, url,
                ], timeout=timeout + 15)
                ok = code == 0
                if not ok:
                    log_message("wget download failed: %s" % output[-500:])
            if not ok:
                ok = _download_with_urllib(url, partial, timeout)
            if ok and os.path.exists(partial) and os.path.getsize(partial) > 256:
                try:
                    if os.path.exists(target_path):
                        os.remove(target_path)
                except Exception:
                    pass
                shutil.move(partial, target_path)
                return True
        except Exception as error:
            log_message("download error %s: %s" % (url, error))
            if log_cb:
                log_cb("Błąd pobierania: %s" % error)
        if attempt + 1 < max(int(retries), 1):
            time.sleep(1.5)
    try:
        if os.path.exists(partial):
            os.remove(partial)
    except Exception:
        pass
    return False


def validate_xmltv_file(path):
    """Stream-validate the complete XMLTV document without loading it into RAM."""
    if not path or not os.path.exists(path) or os.path.getsize(path) < 256:
        return False, "empty"
    opener = gzip.open if to_text(path).lower().endswith(".gz") else open
    channels = 0
    programmes = 0
    root_seen = False
    try:
        with opener(path, "rb") as handle:
            context = ET.iterparse(handle, events=("start", "end"))
            root = None
            for event, elem in context:
                if root is None and event == "start":
                    root = elem
                tag = local_tag(elem.tag)
                if event == "start" and not root_seen:
                    root_seen = True
                    if tag != "tv":
                        return False, "root:%s" % tag
                elif event == "end":
                    if tag == "channel":
                        channels += 1
                    elif tag == "programme":
                        programmes += 1
                    elem.clear()
                    if root is not None and tag == "programme" and programmes % 250 == 0:
                        root.clear()
        if not root_seen:
            return False, "no-root"
        if channels < 1:
            return False, "no-channels"
        if programmes < 1:
            return False, "no-programmes"
        return True, "xmltv channels=%s programmes=%s" % (channels, programmes)
    except Exception as error:
        log_message("XMLTV validation error: %s" % error)
        return False, to_text(error)


def probe_url(url, timeout=25):
    """Small network health probe. Does not download the whole EPG."""
    started = time.time()
    try:
        request = Request(url, headers={"User-Agent": "SimpleIPTVEPG/3.0", "Range": "bytes=0-65535"})
        response = urlopen(request, timeout=timeout)
        try:
            chunk = response.read(65536) or b""
            code = getattr(response, "code", 200) or 200
            content_type = ""
            try:
                content_type = response.headers.get("Content-Type", "") or ""
            except Exception:
                pass
        finally:
            try:
                response.close()
            except Exception:
                pass
        elapsed = int((time.time() - started) * 1000)
        if int(code) >= 400 or len(chunk) < 16:
            return False, "HTTP %s" % code, elapsed
        if to_text(url).lower().endswith(".gz") and not chunk.startswith(b"\x1f\x8b"):
            return False, "brak nagłówka GZIP", elapsed
        return True, "HTTP %s %s" % (code, content_type), elapsed
    except Exception as error:
        return False, to_text(error), int((time.time() - started) * 1000)


def _append_unique_event(target, payload, seen):
    signature = tuple(payload[:4])
    if signature in seen:
        return
    seen.add(signature)
    target.append(payload)


def _get_sat_epg_events_main(sat_ref, start_ts, end_ts):
    from enigma import eEPGCache, eServiceReference
    out = []
    seen = set()
    cache = eEPGCache.getInstance()
    if cache is None:
        return out
    ref = eServiceReference(to_text(sat_ref))
    try:
        if cache.startTimeQuery(ref, int(start_ts)) == 0:
            safety = 0
            while safety < 4096:
                safety += 1
                event = cache.getNextTimeEntry()
                if event is None:
                    break
                start = int(event.getBeginTime() or 0)
                duration = int(event.getDuration() or 0)
                if start <= 0 or duration <= 0:
                    continue
                if start > int(end_ts):
                    break
                title = to_text(event.getEventName() or "")
                desc = to_text(event.getShortDescription() or "")
                try:
                    extended = to_text(event.getExtendedDescription() or "")
                    if extended and extended not in desc:
                        desc = (desc + " " + extended).strip()
                except Exception:
                    pass
                _append_unique_event(out, (start, duration, title[:240], desc[:2048], 0), seen)
    except Exception as error:
        log_message("SAT startTimeQuery error: %s" % error)
        try:
            events = cache.lookupEvent(["IBDCT", (to_text(sat_ref), 0, int(start_ts), int(end_ts))]) or []
            for item in events:
                start = int(item[1]) if len(item) > 1 else 0
                duration = int(item[2]) if len(item) > 2 else 0
                title = to_text(item[4] if len(item) > 4 else "")
                desc = to_text(item[5] if len(item) > 5 else "")
                if start > 0 and duration > 0 and start <= int(end_ts):
                    _append_unique_event(out, (start, duration, title[:240], desc[:2048], 0), seen)
        except Exception as second:
            log_message("SAT lookupEvent error: %s" % second)
    return out


def _build_sat_index(sat_services):
    exact_index = {}
    token_index = {}
    entries = {}
    for service in sat_services or []:
        ref = service.get("full_ref")
        if not ref:
            continue
        candidates = set(service.get("candidates") or [])
        for variant in name_variants(service.get("name", "")):
            compact = compact_name(variant)
            if compact:
                candidates.add(compact)
        for candidate in candidates:
            exact_index.setdefault(candidate, []).append(ref)
        tokens = set(service.get("tokens") or tokenize(service.get("name", "")))
        for token in tokens:
            token_index.setdefault(token, set()).add(ref)
        entries[ref] = {"ref": ref, "name": service.get("name", ""), "candidates": candidates, "tokens": tokens, "norm": service.get("norm", "")}
    return exact_index, token_index, entries


def _score_sat_candidate(iptv_service, sat_entry):
    left_candidates = set(iptv_service.get("candidates") or [])
    right_candidates = set(sat_entry.get("candidates") or [])
    if iptv_service.get("norm") and iptv_service.get("norm") == sat_entry.get("norm"):
        return 1.0
    best = 0.0
    for left in list(left_candidates)[:10]:
        for right in list(right_candidates)[:10]:
            if left == right:
                return 1.0
            if left.startswith(right) or right.startswith(left):
                best = max(best, 0.96)
            elif left in right or right in left:
                best = max(best, 0.92)
            else:
                best = max(best, difflib.SequenceMatcher(None, left, right).ratio())
    overlap = len(set(iptv_service.get("tokens") or []) & set(sat_entry.get("tokens") or []))
    if overlap:
        best = max(best, 0.54 + 0.12 * min(overlap, 3))
    return best


def _candidate_sat_refs(iptv_service, sat_index):
    exact_index, token_index, entries = sat_index
    result = []
    seen = set()
    for candidate in iptv_service.get("candidates") or []:
        for ref in exact_index.get(candidate, []) or []:
            if ref not in seen:
                result.append((1.0, ref))
                seen.add(ref)
    if result:
        return result[:3]
    pool = set()
    for token in sorted(list(set(iptv_service.get("tokens") or [])), key=lambda item: (-len(item), item))[:5]:
        pool.update(token_index.get(token, set()))
        if len(pool) >= 80:
            break
    scored = []
    for ref in pool:
        entry = entries.get(ref)
        if entry:
            score = _score_sat_candidate(iptv_service, entry)
            if score >= 0.90:
                scored.append((score, ref))
    scored.sort(key=lambda item: (-item[0], item[1]))
    # Reject ambiguous SAT fuzzy matches.
    if len(scored) > 1 and scored[0][0] < 0.985 and (scored[0][0] - scored[1][0]) < 0.03:
        return []
    return scored[:3]


def _import_events_main(payload_by_ref):
    from enigma import eEPGCache, eServiceReference
    cache = eEPGCache.getInstance()
    if cache is None:
        return {"services": 0, "events": 0, "errors": 1}
    service_count = 0
    event_count = 0
    errors = 0
    for service_ref, items in payload_by_ref.items():
        cleaned = []
        seen = set()
        for event in sorted(items, key=lambda entry: (entry[0], entry[1], entry[2])):
            start, duration, title, desc, genre = event
            signature = (int(start), int(duration), to_text(title), to_text(desc))
            if signature in seen:
                continue
            seen.add(signature)
            cleaned.append((int(start), int(duration), to_text(title)[:240], "", to_text(desc)[:2048], int(genre or 0)))
        if not cleaned:
            continue
        try:
            if hasattr(cache, "importEvents"):
                # Enigma2's importEvents expects a sequence of service references.
                # Passing a bare string can cause a failed or invisible import.
                cache.importEvents((to_text(service_ref),), tuple(cleaned))
            elif hasattr(cache, "importEvent"):
                cache.importEvent(to_text(service_ref), tuple(cleaned))
            else:
                raise RuntimeError("eEPGCache importEvents/importEvent unavailable")
            service_count += 1
            event_count += len(cleaned)
        except Exception as error:
            errors += 1
            log_message("importEvents failed (service hash %s): %s" % (
                hashlib.sha256(to_bytes(service_ref)).hexdigest()[:10], error))
    return {"services": service_count, "events": event_count, "errors": errors}


def verify_epg_main(refs):
    """Check that imported data is actually queryable on live Enigma2."""
    try:
        from enigma import eEPGCache, eServiceReference
        cache = eEPGCache.getInstance()
        if cache is None:
            return {"checked": 0, "visible": 0}
        visible = 0
        checked = 0
        for ref in list(refs)[:16]:
            try:
                checked += 1
                item = cache.lookupEventTime(eServiceReference(to_text(ref)), int(time.time()))
                if item is not None:
                    visible += 1
            except Exception:
                pass
        return {"checked": checked, "visible": visible}
    except Exception:
        return {"checked": 0, "visible": 0}


def save_epg_cache_main():
    try:
        from enigma import eEPGCache
        cache = eEPGCache.getInstance()
        if cache is not None and hasattr(cache, "save"):
            cache.save()
            return True
    except Exception as error:
        log_message("EPG cache save failed: %s" % error)
    return False


class SafeEPGInjector(object):
    def __init__(self, main_call):
        self.main_call = main_call
        self.events_buffer = {}
        self.total_events = 0
        self.total_services = set()
        self.errors = 0

    def add_event(self, service_ref, event_data):
        start, duration, title, desc, genre = event_data
        if int(start) <= 0 or int(duration) <= 0:
            return
        key = to_text(service_ref)
        self.events_buffer.setdefault(key, []).append((int(start), int(duration), to_text(title), to_text(desc), int(genre or 0)))

    def commit(self):
        if not self.events_buffer:
            return {"services": 0, "events": 0, "errors": 0}
        payload = self.events_buffer
        self.events_buffer = {}
        try:
            result = self.main_call(_import_events_main, payload, timeout=120)
        except Exception as error:
            log_message("main-thread EPG injection failed: %s" % error)
            result = {"services": 0, "events": 0, "errors": 1}
        self.total_events += int(result.get("events", 0))
        self.errors += int(result.get("errors", 0))
        for ref in payload.keys():
            self.total_services.add(ref)
        return result


def clone_sat_to_iptv(injector, iptv_services, sat_services, days_ahead=3, main_call=None, log_cb=None):
    if not main_call:
        return {"injected_refs": set(), "channels": 0, "events": 0}
    now_ts = int(time.time()) - 3600
    end_ts = int(time.time()) + max(int(days_ahead), 1) * 86400
    sat_index = _build_sat_index(sat_services)
    sat_events_cache = {}
    injected_refs = set()
    channels = 0
    events_count = 0
    for index, service in enumerate(iptv_services or []):
        candidates = _candidate_sat_refs(service, sat_index)
        chosen_events = []
        for score, sat_ref in candidates:
            if sat_ref not in sat_events_cache:
                try:
                    sat_events_cache[sat_ref] = main_call(_get_sat_epg_events_main, sat_ref, now_ts, end_ts, timeout=30)
                except Exception as error:
                    log_message("SAT query failed: %s" % error)
                    sat_events_cache[sat_ref] = []
            if sat_events_cache.get(sat_ref):
                chosen_events = sat_events_cache[sat_ref]
                break
        if chosen_events:
            ref = service.get("full_ref")
            for payload in chosen_events:
                injector.add_event(ref, payload)
                events_count += 1
            injected_refs.add(ref)
            channels += 1
        if (index + 1) % 100 == 0:
            injector.commit()
            if log_cb:
                log_cb("SAT → IPTV: %s/%s | kanałów: %s" % (index + 1, len(iptv_services or []), channels))
    injector.commit()
    return {"injected_refs": injected_refs, "channels": channels, "events": events_count}


def genre_code(categories):
    text = " ".join([to_text(item).lower() for item in (categories or [])])
    rules = [
        (("movie", "film", "cinema", "drama", "serial"), 0x10),
        (("news", "wiadomo", "inform", "current affairs"), 0x20),
        (("show", "game show", "variety", "reality"), 0x30),
        (("sport", "football", "soccer", "tennis", "boxing"), 0x40),
        (("children", "kids", "dzieci", "cartoon", "animation"), 0x50),
        (("music", "muzyk", "concert"), 0x60),
        (("arts", "culture", "kultur", "performing"), 0x70),
        (("social", "politic", "econom", "relig"), 0x80),
        (("education", "science", "documentary", "dokument", "nature"), 0x90),
        (("leisure", "travel", "cooking", "cook", "hobby"), 0xA0),
    ]
    for needles, code in rules:
        for needle in needles:
            if needle in text:
                return code
    return 0


class EPGParser(object):
    def __init__(self, source_path):
        self.source_path = source_path

    def parse_timestamp(self, xmltv_date):
        value = to_text(xmltv_date).strip()
        if not value:
            return 0
        match = re.match(r"^(\d{8,14})(?:\s*([+-]\d{2}:?\d{2}|Z))?", value)
        if not match:
            return 0
        stamp, offset = match.groups()
        formats = {8: "%Y%m%d", 10: "%Y%m%d%H", 12: "%Y%m%d%H%M", 14: "%Y%m%d%H%M%S"}
        fmt = formats.get(len(stamp))
        if not fmt:
            return 0
        try:
            dt = datetime.datetime.strptime(stamp, fmt)
            if offset == "Z":
                return int(calendar.timegm(dt.timetuple()))
            if offset:
                clean = offset.replace(":", "")
                sign = 1 if clean.startswith("+") else -1
                hours = int(clean[1:3])
                minutes = int(clean[3:5])
                seconds = sign * ((hours * 60 + minutes) * 60)
                return int(calendar.timegm(dt.timetuple()) - seconds)
            return int(time.mktime(dt.timetuple()))
        except Exception:
            return 0

    def iter_events(self, mapping, days_ahead=3, progress_cb=None):
        if not mapping or not self.source_path or not os.path.exists(self.source_path):
            return
        opener = gzip.open if to_text(self.source_path).lower().endswith(".gz") else open
        now_ts = int(time.time()) - 6 * 3600
        max_ts = int(time.time()) + max(int(days_ahead), 1) * 86400
        processed = 0
        matched = 0
        with opener(self.source_path, "rb") as handle:
            context = ET.iterparse(handle, events=("start", "end"))
            root = None
            for event_type, elem in context:
                if root is None and event_type == "start":
                    root = elem
                if event_type != "end" or local_tag(elem.tag) != "programme":
                    continue
                processed += 1
                channel_id = to_text(elem.get("channel") or "")
                refs = mapping.get(channel_id)
                if refs:
                    start = self.parse_timestamp(elem.get("start"))
                    stop = self.parse_timestamp(elem.get("stop"))
                    if start > 0 and stop > start and start <= max_ts and stop >= now_ts:
                        title = ""
                        subtitle = ""
                        short_desc = ""
                        long_desc = ""
                        categories = []
                        for child in list(elem):
                            tag = local_tag(child.tag)
                            text = to_text(child.text or "").strip()
                            if tag == "title" and not title:
                                title = text
                            elif tag in ("sub-title", "subtitle") and not subtitle:
                                subtitle = text
                            elif tag == "desc":
                                if not short_desc:
                                    short_desc = text
                                elif len(text) > len(long_desc):
                                    long_desc = text
                            elif tag == "category" and text:
                                categories.append(text)
                        desc = long_desc or short_desc
                        if subtitle and subtitle.lower() not in desc.lower():
                            desc = (subtitle + "\n" + desc).strip()
                        payload = (int(start), int(stop - start), title[:240], desc[:2048], genre_code(categories))
                        for ref in refs:
                            matched += 1
                            yield ref, payload, channel_id
                elem.clear()
                if root is not None and processed % 250 == 0:
                    root.clear()
                if progress_cb and processed % 50000 == 0:
                    progress_cb("XMLTV: %s programów | dopasowań: %s" % (processed, matched))


def load_overrides():
    payload = load_json(OVERRIDES_FILE, {})
    return payload if isinstance(payload, dict) else {}


def read_remote_version(timeout=20):
    try:
        request = Request(REMOTE_VERSION_URL, headers={"User-Agent": "SimpleIPTVEPG/3.0"})
        response = urlopen(request, timeout=timeout)
        try:
            data = to_text(response.read(128)).strip()
        finally:
            try:
                response.close()
            except Exception:
                pass
        if re.match(r"^\d+(?:\.\d+){1,3}$", data):
            return data
    except Exception as error:
        log_message("remote version check failed: %s" % error)
    return ""


def _version_tuple(value):
    out = []
    for part in to_text(value).split("."):
        try:
            out.append(int(part))
        except Exception:
            out.append(0)
    return tuple(out)


def is_newer_version(remote, local):
    return _version_tuple(remote) > _version_tuple(local)


def safe_update_plugin(log_cb=None):
    """Explicit updater. TLS verification is never disabled."""
    commands = []
    local_candidates = [
        "/tmp/simpleiptvepg_latest.ipk", "/tmp/simpleiptvepg_update.ipk",
        "/tmp/%s.ipk" % PACKAGE_NAME, "/media/hdd/simpleiptvepg_latest.ipk",
    ]
    opkg = command_exists("opkg")
    if opkg:
        for candidate in local_candidates:
            if os.path.exists(candidate):
                commands.append([opkg, "install", "--force-reinstall", "--force-overwrite", candidate])
        # Do not fetch unspecified package versions from third-party feeds:
        # an older feed could silently replace this new AIO build.
    for command in commands:
        code, output = run_command(command, timeout=600)
        if log_cb:
            log_cb("$ %s" % " ".join(command))
            if output:
                log_cb(output[-800:])
        if code == 0:
            return True, output or "OK"

    from .constants import PLUGIN_VERSION
    remote_version = read_remote_version()
    if not remote_version or not is_newer_version(remote_version, PLUGIN_VERSION):
        return False, "Repozytorium nie zawiera nowszej wersji. Zainstaluj IPK ręcznie lub zaktualizuj repozytorium."
    ensure_dir(TMP_DIR)
    installer = os.path.join(TMP_DIR, "installer.sh")
    try:
        if os.path.exists(installer):
            os.remove(installer)
    except Exception:
        pass
    if not download_file(REMOTE_INSTALLER_URL, installer, timeout=60, retries=1, log_cb=log_cb):
        return False, "Nie udało się pobrać instalatora z oficjalnego repozytorium."
    try:
        size = os.path.getsize(installer)
        with io_open(installer, "r") as handle:
            head = handle.read(min(size, 240000))
        lowered = head.lower()
        if size < 40 or size > 250000 or "simpleiptv_epg" not in lowered or "olioli2013" not in lowered:
            try:
                os.remove(installer)
            except Exception:
                pass
            return False, "Pobrany instalator nie przeszedł walidacji bezpieczeństwa."
        digest = hashlib.sha256(to_bytes(head)).hexdigest()
        if log_cb:
            log_cb("Installer SHA-256: %s" % digest)
        shell = command_exists("sh") or "/bin/sh"
        code, output = run_command([shell, installer], timeout=1800)
        try:
            os.remove(installer)
        except Exception:
            pass
        if log_cb and output:
            log_cb(output[-1500:])
        return (code == 0), (output or ("OK" if code == 0 else "Installer failed"))
    except Exception as error:
        try:
            if os.path.exists(installer):
                os.remove(installer)
        except Exception:
            pass
        return False, to_text(error)
