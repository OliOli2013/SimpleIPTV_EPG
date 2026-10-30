# -*- coding: utf-8 -*-
"""Explicitly opted-in, reversible repair of IPTV EPG identities in bouquets.

Does not run on automatic import. Never modifies DVB/SAT entries, streams,
service type, names, programme data, or playback URLs. Enigma2 GUI needs restart.
"""
from __future__ import absolute_import, print_function
import datetime
import hashlib
import json
import os
import re
import shutil
import tempfile

from .epgcore import is_iptv_ref, compact_name


def _int16(raw):
    return (raw[0] if isinstance(raw[0], int) else ord(raw[0])) * 256 + (raw[1] if isinstance(raw[1], int) else ord(raw[1]))


def _fields(ref):
    fields = ref.split(':', 10)
    if len(fields) != 11:
        return None, None
    try:
        identity = tuple(int(fields[i], 16) for i in (3, 4, 5, 6))
    except ValueError:
        return None, None
    return fields, identity


def _entries(base):
    names = sorted(name for name in os.listdir(base) if name.startswith('userbouquet.') and name.endswith('.tv'))
    all_files = []
    for filename in names:
        path = os.path.join(base, filename)
        with open(path, 'rb') as handle:
            raw = handle.read()
        # Split bytes conservatively; keep original line endings and all metadata.
        lines = raw.splitlines(True)
        rows = []
        for i, rawline in enumerate(lines):
            if not rawline.startswith(b'#SERVICE '):
                continue
            value = rawline[9:].rstrip(b'\r\n')
            try:
                ref = value.decode('utf-8')
            except Exception:
                ref = value.decode('latin-1')
            fields, identity = _fields(ref)
            if fields is None:continue
            name = ''
            if i+1 < len(lines) and lines[i+1].startswith(b'#DESCRIPTION '):
                name = lines[i+1][13:].decode('utf-8', 'replace').strip()
            rows.append((i, ref, fields, identity, name))
        all_files.append((filename, raw, lines, rows))
    return all_files


def plan_repair(base='/etc/enigma2'):
    """Stable mapping original ref->updated ref; never writes in preview."""
    files = _entries(base)
    sat_keys = set()
    iptv_by_identity = {}
    all_keys = set()
    for _fn, _raw, _lines, rows in files:
        for _i, ref, fields, key, name in rows:
            if key and any(key):
                all_keys.add(key)
            if is_iptv_ref(ref):
                if key and any(key):
                    iptv_by_identity.setdefault(key, set()).add(compact_name(name or fields[-1]))
            elif fields[0] == '1' and key and any(key):
                sat_keys.add(key)
    mapping = {}
    reasons = {'zero_identity': 0, 'sat_collision': 0, 'iptv_collision': 0}
    seen = set()
    for _fn, _raw, _lines, rows in files:
        for _i, ref, fields, key, name in rows:
            if not is_iptv_ref(ref) or ref in seen:
                continue
            seen.add(ref)
            reason = None
            if not key or not any(key):reason = 'zero_identity'
            elif key in sat_keys: reason = 'sat_collision'
            elif len(iptv_by_identity.get(key, ())) > 1: reason = 'iptv_collision'
            if not reason:continue
            seed = hashlib.sha256(ref.encode('utf-8')).digest()
            sid = _int16(seed[0:2]) or 1
            tsid = _int16(seed[2:4]) or 1
            onid = _int16(seed[4:6]) or 1
            namespace = 0xEEE00000 | _int16(seed[6:8])
            candidate = (sid, tsid, onid, namespace)
            while candidate in all_keys:
                sid = (sid + 1) & 0xffff or 1
                candidate = (sid, tsid, onid, namespace)
            all_keys.add(candidate)
            new_fields = list(fields)
            for offset, value in zip((3,4,5,6),candidate):
                new_fields[offset] = '%X' % value
            mapping[ref] = ':'.join(new_fields)
            reasons[reason] += 1
    affected = sum(1 for _fn, _raw, _lines, rows in files if any(ref in mapping for _i, ref, _fields, _key, _name in rows))
    return mapping, {'unique_iptv_references': len(mapping), 'files': affected, 'reasons': reasons}, files


def repair(base='/etc/enigma2', dry_run=True):
    mapping, stats, files = plan_repair(base)
    if dry_run or not mapping:
        return stats
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = os.path.join(base, 'simpleiptvepg_backups', stamp)
    os.makedirs(backup)
    changed = []
    temp_files = []
    try:
        for filename, raw, lines, rows in files:
            change = False
            for i, ref, _fields, _key, _name in rows:
                if ref not in mapping:continue
                tail = b'\r\n' if lines[i].endswith(b'\r\n') else (b'\n' if lines[i].endswith(b'\n') else b'')
                lines[i] = b'#SERVICE ' + mapping[ref].encode('utf-8') + tail
                change = True
            if not change:continue
            shutil.copy2(os.path.join(base, filename), os.path.join(backup,filename))
            fd,tmp = tempfile.mkstemp(prefix='.simpleiptvepg-',dir=base)
            temp_files.append(tmp)
            with os.fdopen(fd,'wb') as handle:
                handle.write(b''.join(lines))
                handle.flush();os.fsync(handle.fileno())
            os.chmod(tmp, os.stat(os.path.join(base,filename)).st_mode & 0o777)
            changed.append((os.path.join(base,filename),tmp))
        # Keep restore metadata separately; never export stream URLs in public reports.
        with open(os.path.join(backup,'README.txt'),'w') as handle:
            handle.write('Original userbouquet files, before optional IPTV reference repair.\n')
            handle.write('Restore ONLY after checking whether lists changed since repair.\n')
        for dst,tmp in changed:
            os.rename(tmp,dst)
        stats['backup'] = backup
        stats['restart_gui_required'] = True
        return stats
    except Exception:
        # Failed mid-write: restore precisely the files backed up in this run.
        for dst,_tmp in changed:
            original = os.path.join(backup,os.path.basename(dst))
            if os.path.isfile(original):shutil.copy2(original,dst)
        raise
    finally:
        for tmp in temp_files:
            try: os.remove(tmp)
            except OSError:pass
