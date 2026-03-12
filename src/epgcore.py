# -*- coding: utf-8 -*-
import datetime
import difflib
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import xml.etree.cElementTree as ET

from enigma import eEPGCache, eServiceCenter, eServiceReference

LOG_FILE = "/tmp/simple_epg.log"
TMP_DIR = "/tmp/simpleiptvepg"
PACKAGE_NAME = "enigma2-plugin-extensions-simpleiptvepg"
GITHUB_INSTALLER_URL = "https://raw.githubusercontent.com/OliOli2013/SimpleIPTV_EPG/main/installer.sh"

POLISH_MAP = {
    u"Ą": "A", u"Ć": "C", u"Ę": "E", u"Ł": "L", u"Ń": "N", u"Ó": "O", u"Ś": "S", u"Ź": "Z", u"Ż": "Z",
    u"ą": "A", u"ć": "C", u"ę": "E", u"ł": "L", u"ń": "N", u"ó": "O", u"ś": "S", u"ź": "Z", u"ż": "Z",
}

NOISE_WORDS = set([
    "HD", "FHD", "FULLHD", "UHD", "4K", "HEVC", "H265", "H264", "SD", "PL", "POL", "POLSKA", "TV", "LIVE", "VIP",
    "BACKUP", "TEST", "RAW", "LEKTOR", "DUB", "SUB", "ORIGINAL", "OTV", "ORG", "MULTI", "KANAŁ", "KANAL",
    "EU", "EUROPE", "INTERNATIONAL", "INT", "CHANNEL", "VIP", "PLUSX", "OTT", "MPEGTS", "DASH", "HLS",
    "1080P", "720P", "576P", "50FPS", "60FPS", "X264", "X265", "AAC", "AC3", "EAC3", "DVB",
])

MANUAL_ALIASES = {
    "CANALPLUS": ["CANAL PLUS", "C+", "CANAL+"],
    "CANALPLUSDOCUMENT": ["CANAL+ DOKUMENT", "CANAL PLUS DOKUMENT"],
    "CANALPLUSFILM": ["CANAL+ FILM", "CANAL PLUS FILM"],
    "CANALPLUSSPORT": ["CANAL+ SPORT", "CANAL PLUS SPORT"],
    "TVP1": ["TVP 1"],
    "TVP2": ["TVP 2"],
    "TVP3": ["TVP 3"],
    "TVN7": ["TVN 7"],
    "TVN24": ["TVN 24"],
    "POLSAT2": ["POLSAT 2"],
    "POLSATNEWS2": ["POLSAT NEWS 2"],
    "ELEVENSPORTS1": ["ELEVEN SPORTS 1"],
    "ELEVENSPORTS2": ["ELEVEN SPORTS 2"],
    "ELEVENSPORTS3": ["ELEVEN SPORTS 3"],
    "ELEVENSPORTS4": ["ELEVEN SPORTS 4"],
    "EUROSPORT1": ["EUROSPORT 1"],
    "EUROSPORT2": ["EUROSPORT 2"],
    "HISTORY2": ["HISTORY 2", "H2"],
}


def ensure_temp_dir():
    try:
        if not os.path.isdir(TMP_DIR):
            os.makedirs(TMP_DIR)
    except Exception:
        pass


def log_message(message):
    try:
        with open(LOG_FILE, "a") as handle:
            handle.write("[%s] %s\n" % (datetime.datetime.now().strftime("%H:%M:%S"), str(message)))
    except Exception:
        pass


def load_json(path):
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def atomic_write_json(payload, path):
    try:
        directory = os.path.dirname(path) or "/tmp"
        if not os.path.isdir(directory):
            os.makedirs(directory)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        shutil.move(tmp_path, path)
        return True
    except Exception as error:
        log_message("atomic_write_json error: %s" % error)
        return False


def _replace_polish(value):
    for src, dst in POLISH_MAP.items():
        value = value.replace(src, dst)
    return value


def simplify_name(text):
    if text is None:
        return ""
    value = _replace_polish(str(text).upper())
    value = re.sub(r"\[[^\]]*\]", " ", value)
    value = re.sub(r"\([^\)]*\)", " ", value)
    value = value.replace("&", " AND ").replace("+", " PLUS ")
    value = value.replace("CANAL+", "CANAL PLUS ")
    value = value.replace("C+", "CANAL PLUS ")
    value = value.replace("TVP1", "TVP 1 ").replace("TVP2", "TVP 2 ").replace("TVP3", "TVP 3 ")
    value = value.replace("TVN7", "TVN 7 ").replace("TVN24", "TVN 24 ")
    value = re.sub(r"\bS0([1-9])\b", r"S\1", value)
    value = re.sub(r"\bE0([1-9])\b", r"E\1", value)
    value = re.sub(r"\.(?:[A-Z0-9]{1,3})\b", " ", value)
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    raw_tokens = value.split()
    tokens = []
    for token in raw_tokens:
        if token in NOISE_WORDS:
            continue
        if len(token) == 1 and not token.isdigit():
            continue
        if re.match(r"^(?:19|20)\d{2}$", token):
            continue
        tokens.append(token)
    while tokens and len(tokens[-1]) == 1 and not tokens[-1].isdigit():
        tokens.pop()
    return " ".join(tokens).strip()


def compact_name(text):
    return simplify_name(text).replace(" ", "")


def tokenize(text):
    return [token for token in simplify_name(text).split() if len(token) >= 2]


def name_variants(text):
    base = simplify_name(text)
    compact = base.replace(" ", "")
    variants = set()
    if base:
        variants.add(base)
        variants.add(compact)
        variants.add(base.replace(" PLUS ", " "))
        variants.add(base.replace(" PLUS ", "+"))
        variants.add(re.sub(r"\bTVP\s+(\d)\b", r"TVP\1", base))
        variants.add(re.sub(r"\bTVN\s+(\d+)\b", r"TVN\1", base))
        variants.add(base.replace(" TWO ", " 2 "))
        variants.add(base.replace(" ONE ", " 1 "))
    for key, values in MANUAL_ALIASES.items():
        if compact == key:
            for item in values:
                variants.add(simplify_name(item))
                variants.add(compact_name(item))
    return [item for item in variants if item]


def extract_ref_hints(ref):
    if not ref:
        return []
    decoded = urllib.parse.unquote(str(ref))
    hints = []
    patterns = [
        r"tvg-id=([^&:]+)",
        r"tvg-name=([^&:]+)",
        r"epg_id=([^&:]+)",
        r"channel-id=([^&:]+)",
        r"serviceid=([^&:]+)",
        r"xmltv=([^&:]+)",
        r"name=([^&:]+)",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, decoded, flags=re.IGNORECASE):
            hints.append(match)
    parts = decoded.split(":")
    if parts:
        tail = parts[-1]
        if tail and "http" not in tail.lower():
            hints.append(tail)
    return [item for item in hints if item]


def is_iptv_ref(ref):
    lower = str(ref or "").lower()
    return (
        "4097:" in lower or "5001:" in lower or "5002:" in lower or "8193:" in lower
        or "http" in lower or "https" in lower or "%3a" in lower or "rtmp" in lower or "rtsp" in lower
    )


def is_live_iptv(ref, name):
    lower_ref = str(ref or "").lower()
    upper_name = str(name or "").upper()
    for marker in ["/movie/", "/series/", "/vod/", "type=movie", "type=series", "catchup", "timeshift"]:
        if marker in lower_ref:
            return False
    for marker in [" VOD", "SERIALE", "SERIAL", "XXX VOD", "KINO VOD", "FILMY VOD"]:
        if marker in upper_name:
            return False
    return True


def _service_candidates_from_name_and_ref(name, ref):
    out = []
    seen = set()
    raw = list(extract_ref_hints(ref)) + [name]
    for item in raw:
        for variant in name_variants(item):
            compact = variant.replace(" ", "")
            if compact and compact not in seen:
                seen.add(compact)
                out.append(compact)
    return out


def build_service_entry(ref, name):
    return {
        "full_ref": ref,
        "name": name,
        "norm": compact_name(name),
        "tokens": tokenize(name),
        "candidates": _service_candidates_from_name_and_ref(name, ref),
    }


def _scan_from_files():
    iptv = []
    sat_services = []
    skipped = 0
    seen = set()
    try:
        filenames = sorted([name for name in os.listdir("/etc/enigma2/") if name.startswith("userbouquet") and name.endswith(".tv")])
    except Exception:
        filenames = []

    for filename in filenames:
        path = os.path.join("/etc/enigma2/", filename)
        current = None
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if line.startswith("#SERVICE "):
                        ref = line.replace("#SERVICE ", "", 1).strip()
                        current = {"ref": ref, "name": ""}
                    elif line.startswith("#DESCRIPTION") and current is not None:
                        current["name"] = line.replace("#DESCRIPTION", "", 1).strip()
                        ref = current.get("ref")
                        name = current.get("name")
                        if not ref or ref in seen or "###" in name or "---" in name:
                            current = None
                            continue
                        seen.add(ref)
                        if is_iptv_ref(ref):
                            if not is_live_iptv(ref, name):
                                skipped += 1
                            else:
                                iptv.append(build_service_entry(ref, name))
                        elif ref.startswith("1:0:"):
                            sat_services.append(build_service_entry(ref, name))
                        current = None
        except Exception as error:
            log_message("scan files error %s: %s" % (path, error))
    return iptv, sat_services, skipped


def _scan_from_memory():
    iptv = []
    sat_services = []
    skipped = 0
    seen_refs = set()
    service_center = eServiceCenter.getInstance()
    root = eServiceReference('1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.tv" ORDER BY bouquet')
    bouquets = service_center.list(root)
    if bouquets is None:
        raise RuntimeError("no bouquets")
    bouquet_items = bouquets.getContent("SN") or []
    for bouquet_ref, _bouquet_name in bouquet_items:
        bouquet_list = service_center.list(eServiceReference(bouquet_ref))
        if bouquet_list is None:
            continue
        for service_ref, service_name in (bouquet_list.getContent("SN") or []):
            if not service_ref or service_ref in seen_refs:
                continue
            if "###" in str(service_name) or "---" in str(service_name):
                continue
            seen_refs.add(service_ref)
            if is_iptv_ref(service_ref):
                if not is_live_iptv(service_ref, service_name):
                    skipped += 1
                    continue
                iptv.append(build_service_entry(service_ref, service_name))
            elif str(service_ref).startswith("1:0:"):
                sat_services.append(build_service_entry(service_ref, service_name))
    return iptv, sat_services, skipped


def _merge_service_lists(primary, secondary):
    seen = set()
    merged = []
    for bucket in (primary or [], secondary or []):
        for item in bucket:
            ref = item.get("full_ref")
            if not ref or ref in seen:
                continue
            seen.add(ref)
            merged.append(item)
    return merged


def _build_sat_exact_map(sat_services):
    sat_map = {}
    for service in sat_services:
        for candidate in service.get("candidates", []) or []:
            sat_map.setdefault(candidate, [])
            if service.get("full_ref") not in sat_map[candidate]:
                sat_map[candidate].append(service.get("full_ref"))
    return sat_map


def scan_bouquet_services():
    file_iptv, file_sat, file_skipped = _scan_from_files()
    mem_iptv, mem_sat, mem_skipped = [], [], 0
    try:
        mem_iptv, mem_sat, mem_skipped = _scan_from_memory()
    except Exception as error:
        log_message("scan_bouquet_services memory fallback: %s" % error)

    iptv = _merge_service_lists(mem_iptv, file_iptv)
    sat_services = _merge_service_lists(mem_sat, file_sat)
    skipped = int(file_skipped) + int(mem_skipped)

    digest = hashlib.md5()
    for item in sorted(iptv, key=lambda entry: entry.get("full_ref", "")):
        digest.update((item.get("full_ref", "") + "|" + item.get("norm", "") + "\n").encode("utf-8", "ignore"))

    sat_digest = hashlib.md5()
    for item in sorted(sat_services, key=lambda entry: entry.get("full_ref", "")):
        sat_digest.update((item.get("full_ref", "") + "|" + item.get("norm", "") + "\n").encode("utf-8", "ignore"))

    return {
        "iptv": iptv,
        "sat_services": sat_services,
        "sat_map": _build_sat_exact_map(sat_services),
        "skipped": skipped,
        "services_signature": digest.hexdigest() + ":" + sat_digest.hexdigest(),
    }


def _download_via_command(command, timeout):
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout + 10)
        return result.returncode == 0
    except Exception:
        return False


def _download_via_urllib(url, target_path, timeout):
    request = urllib.request.Request(url, headers={"User-Agent": "SimpleIPTVEPG/2.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        with open(target_path, "wb") as handle:
            while True:
                chunk = response.read(1024 * 128)
                if not chunk:
                    break
                handle.write(chunk)
    return True


def download_file(url, target_path, timeout=120, retries=2, log_cb=None):
    ensure_temp_dir()
    for attempt in range(retries):
        try:
            if os.path.exists(target_path):
                os.remove(target_path)
        except Exception:
            pass
        try:
            ok = False
            if shutil.which("curl"):
                ok = _download_via_command(["curl", "-f", "-L", "-k", "--connect-timeout", "20", "--max-time", str(timeout), "-A", "SimpleIPTVEPG/2.1", "-o", target_path, url], timeout)
            if not ok and shutil.which("wget"):
                ok = _download_via_command(["wget", "-q", "-O", target_path, "--timeout=%s" % timeout, url], timeout)
            if not ok:
                ok = _download_via_urllib(url, target_path, timeout)
            if ok and os.path.exists(target_path) and os.path.getsize(target_path) > 256:
                return True
        except Exception as error:
            log_message("download_file error (%s): %s" % (url, error))
            if log_cb:
                log_cb("Download error: %s" % error)
        time.sleep(1)
    return False





def update_plugin_package(log_cb=None):
    commands = []
    local_candidates = [
        "/tmp/simpleiptvepg_latest.ipk",
        "/tmp/simpleiptvepg_update.ipk",
        "/tmp/%s.ipk" % PACKAGE_NAME,
        "/media/hdd/simpleiptvepg_latest.ipk",
    ]
    for candidate in local_candidates:
        if os.path.exists(candidate):
            commands.append(["opkg", "install", "--force-reinstall", "--force-overwrite", candidate])
    commands.extend([
        ["opkg", "update"],
        ["opkg", "install", "--force-reinstall", "--force-overwrite", PACKAGE_NAME],
        ["opkg", "upgrade", PACKAGE_NAME],
    ])
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, timeout=600, text=True)
            output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
            if log_cb:
                log_cb("$ %s" % " ".join(command))
                if output:
                    log_cb(output[-600:])
            if result.returncode == 0:
                return True, output or "OK"
        except Exception as error:
            if log_cb:
                log_cb("Update error: %s" % error)
            log_message("update_plugin_package error: %s" % error)

    installer_path = os.path.join(TMP_DIR, "installer.sh")
    os.makedirs(TMP_DIR, exist_ok=True)
    download_commands = [
        ["wget", "--no-check-certificate", "-O", installer_path, GITHUB_INSTALLER_URL],
        ["curl", "-k", "-L", "-o", installer_path, GITHUB_INSTALLER_URL],
    ]
    for command in download_commands:
        try:
            result = subprocess.run(command, capture_output=True, timeout=180, text=True)
            output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
            if log_cb:
                log_cb("$ %s" % " ".join(command))
                if output:
                    log_cb(output[-600:])
            if result.returncode == 0 and os.path.exists(installer_path):
                break
        except Exception as error:
            if log_cb:
                log_cb("Installer download error: %s" % error)
    if os.path.exists(installer_path):
        try:
            os.chmod(installer_path, 0o755)
            result = subprocess.run(["/bin/sh", installer_path], capture_output=True, timeout=1800, text=True)
            output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
            if log_cb:
                log_cb("$ /bin/sh %s" % installer_path)
                if output:
                    log_cb(output[-1200:])
            if result.returncode == 0:
                return True, output or "OK"
            return False, output or "Installer failed"
        except Exception as error:
            if log_cb:
                log_cb("Installer execution error: %s" % error)
            log_message("update_plugin_package installer error: %s" % error)
            return False, str(error)

    return False, "Brak pakietu w feedzie, lokalnego IPK ani instalatora GitHub."


def validate_xmltv_file(path):

    if not path or not os.path.exists(path):
        return False
    opener = gzip.open if str(path).lower().endswith(".gz") else open
    try:
        with opener(path, "rb") as handle:
            chunk = handle.read(4096)
        head = chunk.decode("utf-8", "ignore").lower()
        return "<tv" in head or "<?xml" in head
    except Exception as error:
        log_message("validate_xmltv_file error: %s" % error)
        return False


def _append_unique_event(target, event_tuple, signatures):
    start, duration, title, desc = event_tuple
    signature = (int(start), int(duration), str(title or "")[:240], str(desc or "")[:1024])
    if signature in signatures:
        return
    signatures.add(signature)
    target.append(signature)


def get_sat_epg_events(sat_ref, start_ts, end_ts):
    out = []
    seen = set()
    try:
        cache = eEPGCache.getInstance()
        ref = eServiceReference(str(sat_ref))
        if cache and ref and ref.valid():
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
                        title = event.getEventName() or ""
                        desc = event.getShortDescription() or ""
                        try:
                            ext = event.getExtendedDescription() or ""
                            if ext and ext not in desc:
                                desc = (desc + " " + ext).strip() if desc else ext
                        except Exception:
                            pass
                        _append_unique_event(out, (start, duration, title, desc), seen)
            except Exception as error:
                log_message("get_sat_epg_events startTimeQuery error: %s" % error)

            if not out:
                try:
                    events = cache.lookupEvent(["IBDCT", (str(sat_ref), 0, int(start_ts), int(end_ts))]) or []
                    for item in events:
                        start = int(item[1]) if len(item) > 1 else 0
                        duration = int(item[2]) if len(item) > 2 else 0
                        title = item[4] if len(item) > 4 else ""
                        desc = item[5] if len(item) > 5 else ""
                        if start > 0 and duration > 0 and start <= int(end_ts):
                            _append_unique_event(out, (start, duration, title, desc), seen)
                except Exception as error:
                    log_message("get_sat_epg_events lookupEvent error: %s" % error)
    except Exception as error:
        log_message("get_sat_epg_events fatal: %s" % error)
    return out


def _build_sat_index(sat_services):
    exact_index = {}
    token_index = {}
    entries = {}
    for service in sat_services:
        ref = service.get("full_ref")
        if not ref:
            continue
        candidates = set(service.get("candidates", []) or [])
        for variant in name_variants(service.get("name", "")):
            compact = variant.replace(" ", "")
            if compact:
                candidates.add(compact)
                exact_index.setdefault(compact, []).append(ref)
        tokens = set(service.get("tokens", []) or tokenize(service.get("name", "")))
        for token in tokens:
            token_index.setdefault(token, set()).add(ref)
        entries[ref] = {
            "ref": ref,
            "name": service.get("name", ""),
            "candidates": candidates,
            "tokens": tokens,
            "norm": service.get("norm", ""),
        }
    return exact_index, token_index, entries


def _score_sat_candidate(iptv_service, sat_entry):
    best = 0.0
    iptv_candidates = set(iptv_service.get("candidates", []) or [])
    sat_candidates = set(sat_entry.get("candidates", []) or [])
    iptv_tokens = set(iptv_service.get("tokens", []) or [])
    sat_tokens = set(sat_entry.get("tokens", []) or [])
    overlap = len(iptv_tokens & sat_tokens)
    if overlap:
        best = max(best, 0.46 + 0.11 * min(overlap, 4))
    if iptv_service.get("norm") and iptv_service.get("norm") == sat_entry.get("norm"):
        return 1.0
    for left in list(iptv_candidates)[:8]:
        for right in list(sat_candidates)[:8]:
            if left == right:
                return 1.0
            if left.startswith(right) or right.startswith(left):
                best = max(best, 0.95)
            elif left in right or right in left:
                best = max(best, 0.91)
            else:
                ratio = difflib.SequenceMatcher(None, left, right).ratio()
                if ratio > best:
                    best = ratio
    return best


def _candidate_sat_refs(iptv_service, sat_index):
    exact_index, token_index, entries = sat_index
    result = []
    seen = set()
    for candidate in iptv_service.get("candidates", []) or []:
        for ref in exact_index.get(candidate, []) or []:
            if ref not in seen:
                result.append((1.0, ref))
                seen.add(ref)
    if result:
        return result[:4]

    pool = set()
    for token in sorted(list(set(iptv_service.get("tokens", []) or [])), key=lambda item: (-len(item), item))[:5]:
        pool.update(token_index.get(token, set()))
        if len(pool) >= 96:
            break
    if not pool:
        prefix = (iptv_service.get("norm") or "")[:2]
        if prefix:
            for ref, entry in entries.items():
                if (entry.get("norm") or "").startswith(prefix):
                    pool.add(ref)
                    if len(pool) >= 96:
                        break
    scored = []
    for ref in pool:
        entry = entries.get(ref)
        if not entry:
            continue
        score = _score_sat_candidate(iptv_service, entry)
        if score >= 0.76:
            scored.append((score, ref))
    scored.sort(reverse=True)
    return scored[:4]


def clone_sat_to_iptv(injector, iptv_services, sat_services, days_ahead=3, log_cb=None):
    injected_refs = set()
    sat_events_cache = {}
    cloned_channels = 0
    matched_candidates = 0
    now_ts = int(time.time()) - 3600
    end_ts = int(time.time()) + max(int(days_ahead), 1) * 86400
    sat_index = _build_sat_index(sat_services or [])

    for index, service in enumerate(iptv_services):
        candidates = _candidate_sat_refs(service, sat_index)
        if not candidates:
            continue
        chosen_events = []
        for score, sat_ref in candidates:
            if sat_ref not in sat_events_cache:
                sat_events_cache[sat_ref] = get_sat_epg_events(sat_ref, now_ts, end_ts)
            events = sat_events_cache.get(sat_ref, [])
            if events:
                matched_candidates += 1
                chosen_events = events
                if log_cb and score >= 0.98 and ((index + 1) % 300 == 0):
                    log_cb("SAT exact: %s -> %s" % (service.get("name", ""), sat_ref))
                break
        if not chosen_events:
            continue
        for payload in chosen_events:
            injector.add_event(service.get("full_ref"), payload)
        injected_refs.add(service.get("full_ref"))
        cloned_channels += 1
        if (index + 1) % 200 == 0:
            injector.commit()
            if log_cb:
                log_cb("SAT: %s/%s | sklonowano: %s" % (index + 1, len(iptv_services), cloned_channels))
    injector.commit()
    if log_cb:
        log_cb("SAT match: sklonowane=%s z %s IPTV | SAT refs=%s" % (cloned_channels, len(iptv_services), len(sat_services or [])))
    return {"injected_refs": injected_refs, "channels": cloned_channels, "candidate_hits": matched_candidates}


class EPGParser(object):
    def __init__(self, source_path):
        self.source_path = source_path

    def parse_timestamp(self, xmltv_date):
        if not xmltv_date:
            return 0
        value = str(xmltv_date).strip()
        match = re.match(r"^(\d{14})(?:\s*([+-]\d{4}|Z))?", value)
        if not match:
            return 0
        stamp, offset = match.groups()
        try:
            dt = datetime.datetime.strptime(stamp, "%Y%m%d%H%M%S")
            if offset and offset != "Z":
                sign = 1 if offset.startswith("+") else -1
                hours = int(offset[1:3])
                minutes = int(offset[3:5])
                delta = datetime.timedelta(hours=hours, minutes=minutes)
                tz = datetime.timezone(sign * delta)
                dt = dt.replace(tzinfo=tz)
                return int(dt.timestamp())
            if offset == "Z":
                dt = dt.replace(tzinfo=datetime.timezone.utc)
                return int(dt.timestamp())
            return int(time.mktime(dt.timetuple()))
        except Exception:
            return 0

    def iter_events(self, mapping, days_ahead=3, progress_cb=None):
        if not self.source_path or not os.path.exists(self.source_path):
            return
        opener = gzip.open if str(self.source_path).lower().endswith(".gz") else open
        if not mapping:
            return
        now_ts = int(time.time()) - 6 * 3600
        max_ts = int(time.time()) + max(int(days_ahead), 1) * 86400
        processed = 0
        matched = 0
        try:
            with opener(self.source_path, "rb") as handle:
                context = ET.iterparse(handle, events=("end",))
                for _event, elem in context:
                    if elem.tag != "programme":
                        if elem.tag == "tv":
                            elem.clear()
                        continue
                    processed += 1
                    channel_id = elem.get("channel") or ""
                    refs = mapping.get(channel_id)
                    if refs:
                        start = self.parse_timestamp(elem.get("start"))
                        stop = self.parse_timestamp(elem.get("stop"))
                        if start > 0 and stop > start and start <= max_ts and stop >= now_ts:
                            duration = stop - start
                            title = ""
                            desc = ""
                            for child in elem:
                                if child.tag == "title" and not title:
                                    title = child.text or ""
                                elif child.tag == "desc" and not desc:
                                    desc = child.text or ""
                            payload = (int(start), int(duration), str(title or "")[:240], str(desc or "")[:1024])
                            for service_ref in refs:
                                matched += 1
                                yield service_ref, payload, channel_id
                    elem.clear()
                    if progress_cb and processed % 50000 == 0:
                        progress_cb("XML: %s programów | trafień: %s" % (processed, matched))
        except Exception as error:
            log_message("EPGParser.iter_events error: %s" % error)
            if progress_cb:
                progress_cb("XML parse error: %s" % error)


class EPGInjector(object):
    def __init__(self):
        self.epg_cache = eEPGCache.getInstance()
        self.events_buffer = {}

    def add_event(self, service_ref, event_data):
        start, duration, title, desc = event_data
        if start <= 0 or duration <= 0:
            return
        key = str(service_ref)
        self.events_buffer.setdefault(key, []).append((int(start), int(duration), str(title or "")[:240], "", str(desc or "")[:1024], 0))

    def commit(self):
        if not self.events_buffer:
            return
        for service_ref, items in list(self.events_buffer.items()):
            try:
                cleaned = []
                seen = set()
                for event in sorted(items, key=lambda entry: (entry[0], entry[1], entry[2])):
                    signature = (event[0], event[1], event[2], event[4])
                    if signature in seen:
                        continue
                    seen.add(signature)
                    cleaned.append(event)
                if cleaned:
                    self.epg_cache.importEvents(str(service_ref), cleaned)
            except Exception as error:
                log_message("EPGInjector.commit error for %s: %s" % (service_ref, error))
        self.events_buffer = {}
