# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function

import hashlib
import os
import threading
import time

from twisted.internet import reactor

from .automapper import AutoMapper
from .compat import ensure_dir, spawn_thread, to_text
from .constants import MAPPING_FILE, REPORT_FILE, TMP_DIR
from .epgcore import (
    EPGParser, SafeEPGInjector, clone_sat_to_iptv, download_file,
    load_overrides, probe_url, safe_update_plugin, save_epg_cache_main,
    read_remote_version, is_newer_version, verify_epg_main,
    scan_bouquet_services, source_fingerprint, validate_xmltv_file,
)
from .epgimport_bridge import (
    discover_bmx_sources, import_bmx_mapping, channels_signature, combine_maps, safe_url,
)
from .logger import log_message
from .picons import install_picons
from .epg_autopilot import (choose_country_feeds, country_from_name,
    dedupe_mapping, likely_unscheduled_count)
from .matchguard import filter_unsafe_refs, guard_mapping
from .settings import cfg
from .sources import SOURCE_MAP
from .storage import atomic_write_json, load_json, load_state, save_report, update_state

MAIN_THREAD_IDENT = threading.current_thread().ident


class MainThreadBridge(object):
    def call(self, func, *args, **kwargs):
        timeout = float(kwargs.pop("timeout", 60))
        if threading.current_thread().ident == MAIN_THREAD_IDENT:
            return func(*args, **kwargs)
        done = threading.Event()
        box = {"result": None, "error": None}

        def invoke():
            try:
                box["result"] = func(*args, **kwargs)
            except Exception as error:
                box["error"] = error
            finally:
                done.set()

        reactor.callFromThread(invoke)
        if not done.wait(timeout):
            raise RuntimeError("Timeout waiting for Enigma2 main thread")
        if box["error"] is not None:
            raise box["error"]
        return box["result"]


class EPGWorker(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.task_name = ""
        self.bridge = MainThreadBridge()

    def _log(self, callback, message):
        log_message(message)
        if callback:
            try:
                callback(to_text(message))
            except Exception:
                pass

    def _selected_sources(self):
        source_id = cfg.source_select.value
        if source_id == "BMX_AUTO":
            return [(item["id"], item["url"], item["channels"]) for item in discover_bmx_sources()]
        if source_id == "CUSTOM":
            url = to_text(cfg.custom_url.value).strip()
            if url.startswith("http://") or url.startswith("https://"):
                # Custom XMLTV can also use BMX channel mapping if the URL matches.
                matches = [item for item in discover_bmx_sources() if item['url'] == url]
                return [(source_id, url, matches[0]['channels'] if matches else None)]
            return []
        source = SOURCE_MAP.get(source_id) or SOURCE_MAP.get("AUTO_PL")
        return [(source_id, url, None) for url in (source.get("urls") or [])]

    def _download_source(self, callback):
        sources = self._selected_sources()
        if not sources:
            self._log(callback, "Nie ustawiono prawidłowego źródła XMLTV.")
            return None, None, None, None
        ensure_dir(TMP_DIR)
        for index, (source_id, url, channels) in enumerate(sources):
            suffix = ".xml.gz" if url.lower().split('?', 1)[0].endswith(".gz") else ".xml"
            target = os.path.join(TMP_DIR, "guide-%s%s" % (source_fingerprint(url), suffix))
            self._log(callback, "Źródło %s/%s: %s" % (index + 1, len(sources), safe_url(url)))
            if not download_file(url, target, timeout=240, retries=2, log_cb=callback):
                self._log(callback, "Pobieranie nie powiodło się – próbuję kolejnego źródła.")
                continue
            # Detect GZIP by bytes, not URL suffix (e.g. provider xmltv.php?user=).
            try:
                with open(target, "rb") as probe:
                    compressed = probe.read(2) == b"\x1f\x8b"
                desired = os.path.splitext(target)[0] if not compressed and target.endswith(".gz") else target
                if compressed and not target.endswith(".gz"):
                    desired = target + ".gz"
                if desired != target:
                    if os.path.exists(desired):
                        os.remove(desired)
                    os.rename(target, desired)
                    target = desired
            except Exception as error:
                self._log(callback, "Rozpoznawanie kompresji: %s" % error)
            valid, reason = validate_xmltv_file(target)
            if valid:
                self._log(callback, "XMLTV poprawny: %s" % safe_url(url))
                return target, source_id, url, channels
            self._log(callback, "Odrzucono nieprawidłowy XMLTV (%s)." % reason)
            try:
                os.remove(target)
            except Exception:
                pass
        return None, None, None, None

    def _mapping_cache(self, signature, source_url, sensitivity, channel_sig=""):
        payload = load_json(MAPPING_FILE, {})
        if not isinstance(payload, dict):
            return None, {}
        meta = payload.get("_meta") if isinstance(payload.get("_meta"), dict) else {}
        mapping = payload.get("mapping") if isinstance(payload.get("mapping"), dict) else None
        if not mapping:
            return None, meta
        if meta.get("services_signature") != signature:
            return None, meta
        if meta.get("source_hash") != source_fingerprint(source_url):
            return None, meta
        if meta.get("sensitivity") != sensitivity:
            return None, meta
        if meta.get("channel_signature", "") != channel_sig:
            return None, meta
        if meta.get("mapping_format") != 5:
            return None, meta
        return mapping, meta

    def _save_mapping(self, mapping, signature, source_id, source_url, sensitivity, stats, channel_sig=""):
        payload = {
            "_meta": {
                "services_signature": signature,
                "source_id": source_id,
                "source_url": safe_url(source_url),
                "source_hash": source_fingerprint(source_url),
                "mapping_format": 5,
                "channel_signature": channel_sig,
                "source_fingerprint": source_fingerprint(source_url),
                "sensitivity": sensitivity,
                "saved_at": int(time.time()),
                "groups": int(stats.get("groups", 0)),
                "matched_groups": int(stats.get("matched_groups", 0)),
                "xml_ids": int(stats.get("xml_ids", 0)),
            },
            "mapping": mapping,
        }
        atomic_write_json(payload, MAPPING_FILE)

    def _cleanup_xml(self, path):
        if cfg.keep_xml_cache.value:
            return
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    def _acquire(self, task_name, callback):
        if not self.lock.acquire(False):
            self._log(callback, "Inne zadanie jest już wykonywane.")
            return False
        self.running = True
        self.task_name = task_name
        return True

    def _release(self):
        self.running = False
        self.task_name = ""
        try:
            self.lock.release()
        except Exception:
            pass

    def start_import(self, callback=None, done_callback=None, silent=False, force_mapping=False):
        if not self._acquire("import", callback):
            return False

        def runner():
            ok = False
            result = {}
            try:
                ok, result = self._run_import(callback, force_mapping=force_mapping)
            except Exception as error:
                result = {"error": to_text(error)}
                self._log(callback, "Błąd krytyczny importu: %s" % error)
                update_state(last_attempt=int(time.time()), last_error=to_text(error), last_result="failed")
            finally:
                if not cfg.keep_xml_cache.value:
                    self.clear_temp()
                self._release()
                if done_callback:
                    reactor.callFromThread(done_callback, ok, result, silent)
        spawn_thread(runner, name="SimpleIPTVEPG-import")
        return True

    def _run_import(self, callback, force_mapping=False):
        started = time.time()
        update_state(last_attempt=int(started), last_error="", last_result="running")
        self._log(callback, "Analiza bukietów Enigma2...")
        scan = scan_bouquet_services(main_call=self.bridge.call)
        iptv = scan.get("iptv", [])
        sat = scan.get("sat_services", [])
        skipped = scan.get("skipped", 0)
        signature = scan.get("services_signature", "")
        def dvb_identity(ref):
            fields = to_text(ref).split(':', 10)
            if len(fields) < 11 or not all(fields[i] for i in (3, 4, 5, 6)):
                return None
            try:
                identity = tuple(int(fields[index], 16) for index in (3, 4, 5, 6))
                return identity if any(identity) else None
            except ValueError:
                return None

        sat_keys = set(key for key in (dvb_identity(s.get('full_ref', '')) for s in sat) if key)
        protected = set(s.get('full_ref') for s in iptv if dvb_identity(s.get('full_ref', '')) in sat_keys)
        active_iptv = [service for service in iptv if service.get('full_ref') not in protected]
        active_iptv, ref_guard = filter_unsafe_refs(active_iptv)
        self._log(callback, 'Ochrona IPTV: zerowe/bledne %s, kolizyjne %s, znaczniki %s.' % (
            ref_guard['zero_or_invalid'], ref_guard['colliding_names'], ref_guard['pseudoref']))
        self._log(callback, "Wykryto IPTV live: %s | SAT: %s | pominięte VOD/serie: %s" % (len(iptv), len(sat), skipped))
        if protected:
            self._log(callback, 'Ochrona EPG SAT: %s IPTV współdzieli SID/TSID/ONID/namespace z SAT. Bez importu do tych referencji.' % len(protected))
        if not iptv:
            update_state(last_result="failed", last_error="Brak kanałów IPTV live")
            return False, {"error": "Brak kanałów IPTV live"}

        xml_path, source_id, source_url, native_channels_path = self._download_source(callback)
        if not xml_path:
            pstats = {'created': 0, 'covered': 0, 'skipped': 0}
            if cfg.picons_enabled.value:
                try:
                    pstats = install_picons(iptv, [], sat_services=sat,
                        allow_catalog=cfg.picons_online.value,
                        log_cb=lambda msg: self._log(callback, msg))
                except Exception as error:
                    self._log(callback, 'Picony bez XMLTV: %s' % error)
            update_state(last_result="failed", last_error="Nie udało się pobrać prawidłowego XMLTV")
            save_report({'success': False, 'iptv_services': len(iptv), 'picons': pstats,
                         'error': 'Nie udało się pobrać prawidłowego XMLTV'})
            return False, {"error": "Nie udało się pobrać prawidłowego XMLTV", 'picons': pstats}

        days = int(cfg.import_days.value or "5")
        sensitivity = cfg.mapping_sensitivity.value or "balanced"
        mapping = None
        mapping_stats = {}
        channel_sig = channels_signature(native_channels_path)
        if not force_mapping:
            mapping, _meta = self._mapping_cache(signature, source_url, sensitivity, channel_sig)
        if mapping:
            mapping = dict((cid, [ref for ref in refs if ref not in protected])
                           for cid, refs in mapping.items())
            mapping = dict((cid, refs) for cid, refs in mapping.items() if refs)
            self._log(callback, "Wczytano mapowanie zgodne z aktualnymi bukietami i plikiem BMX.")
            mapping_stats = {"groups": len(iptv), "matched_groups": -1, "xml_ids": len(mapping), "cached": True}
        else:
            native_map = {}
            native_stats = {}
            if native_channels_path:
                self._log(callback, "Dopasowanie XMLTV IDs według BouquetMakerXtream channels.xml...")
                native_map, native_stats = import_bmx_mapping(native_channels_path, active_iptv)
                self._log(callback, "BMX: %s/%s dopasowanych wpisów" % (
                    native_stats.get('bmx_matches', 0), native_stats.get('bmx_channels', 0)))
            self._log(callback, "Mapowanie pozostałych kanałów na podstawie nazw i tvg-id...")
            mapper = AutoMapper(callback, sensitivity=sensitivity, overrides=load_overrides())
            fallback_map, mapping_stats = mapper.generate_mapping(active_iptv, xml_path)
            fallback_map, quality_stats = guard_mapping(fallback_map, active_iptv, xml_path, load_overrides())
            mapping_stats["safe_mapping"] = quality_stats
            self._log(callback, "Kontrola zgodnosci nazw IPTV/XMLTV: przyjete %s, odrzucone %s." % (
                quality_stats["accepted_refs"], quality_stats["rejected_refs"]))
            mapping = combine_maps(native_map, fallback_map)
            mapping_stats.update(native_stats)
            mapping_stats['xml_ids'] = len(mapping)
            mapping_stats['bmx_id_count'] = len(native_map)
            if mapping:
                self._save_mapping(mapping, signature, source_id, source_url, sensitivity, mapping_stats, channel_sig)
            self._log(callback, "Mapowanie: %s XML ID | nierozpoznane po nazwie: %s | niejednoznaczne: %s" % (
                len(mapping or {}), mapping_stats.get("unmatched", 0), mapping_stats.get("ambiguous", 0)))

        mapping, duplicates_removed = dedupe_mapping(mapping or {})
        if duplicates_removed:
            self._log(callback, "Usunieto %s podwojnych wpisow referencji IPTV." % duplicates_removed)
        injector = SafeEPGInjector(self.bridge.call)
        cloned_refs = set()
        sat_stats = {"channels": 0, "events": 0}
        if cfg.clone_sat.value and sat:
            self._log(callback, "Kopiowanie pewnych dopasowań EPG z SAT do IPTV...")
            sat_stats = clone_sat_to_iptv(injector, active_iptv, sat, days_ahead=days, main_call=self.bridge.call, log_cb=callback)
            cloned_refs = sat_stats.get("injected_refs", set())
            self._log(callback, "SAT → IPTV: %s kanałów, %s zdarzeń" % (sat_stats.get("channels", 0), sat_stats.get("events", 0)))

        xml_events = 0
        xml_channels = set()
        xml_refs = set()
        if mapping:
            self._log(callback, "Import XMLTV do pamięci EPG...")
            parser = EPGParser(xml_path)
            buffer_count = 0
            for service_ref, event, channel_id in parser.iter_events(mapping, days_ahead=days, progress_cb=callback):
                if cfg.prefer_sat.value and service_ref in cloned_refs:
                    continue
                injector.add_event(service_ref, event)
                xml_events += 1
                xml_channels.add(channel_id)
                xml_refs.add(service_ref)
                buffer_count += 1
                if buffer_count >= 3500:
                    injector.commit()
                    buffer_count = 0
            injector.commit()

        source_coverage = [{"source": safe_url(source_url), "kind": "primary",
                            "services_with_events": len(xml_refs), "events": xml_events}]
        # Missing IPTV services may be absent from the first VALID XMLTV feed.
        # Use later configured feeds only for uncovered services; never touch SAT.
        picon_mappings = [(xml_path, mapping or {})]
        supplementary_files = []
        extra_sources = []
        country_plan = []
        if cfg.fill_missing.value:
            supplementary_sources = list(self._selected_sources())
            if cfg.source_select.value in ("AUTO_AIO", "AUTO_PL", "AUTO_PL_RICH"):
                uncovered = [entry for entry in active_iptv if entry.get("full_ref") not in xml_refs]
                used = [url for _sid, url, _channels in supplementary_sources]
                country_plan = choose_country_feeds(uncovered, used_urls=used, limit=2, minimum=12)
                supplementary_sources.extend(("AUTO_COUNTRY_" + code, url, None)
                                             for code, url, _count in country_plan)
                if country_plan:
                    self._log(callback, "Dodatkowe EPG wedlug kraju: %s" %
                              ", ".join("%s (%s)" % (code, count) for code, _url, count in country_plan))
            for secondary_id, secondary_url, _channel_file in supplementary_sources:
                if secondary_url == source_url or len(extra_sources) >= 6:
                    continue
                missing = [service for service in active_iptv if service.get('full_ref') not in xml_refs
                           and (not cfg.prefer_sat.value or service.get('full_ref') not in cloned_refs)]
                if secondary_id.startswith('AUTO_COUNTRY_'):
                    country = secondary_id[len('AUTO_COUNTRY_'):]
                    missing = [service for service in missing
                               if country_from_name(service.get('name', '')) == country]
                if not missing:
                    if secondary_id.startswith('AUTO_COUNTRY_'):
                        continue
                    break
                suffix = '.xml.gz' if secondary_url.lower().split('?', 1)[0].endswith('.gz') else '.xml'
                extra_path = os.path.join(TMP_DIR, 'fill-%s%s' % (source_fingerprint(secondary_url), suffix))
                extra_sources.append(safe_url(secondary_url))
                self._log(callback, 'Uzupełnianie braków EPG (%s usług): %s' % (
                    len(missing), safe_url(secondary_url)))
                if not download_file(secondary_url, extra_path, timeout=180, retries=1):
                    continue
                try:
                    with open(extra_path, 'rb') as handle:
                        zipped = handle.read(2) == b'\x1f\x8b'
                    if zipped != extra_path.endswith('.gz'):
                        destination = extra_path + '.gz' if zipped else extra_path[:-3]
                        if os.path.exists(destination):
                            os.remove(destination)
                        os.rename(extra_path, destination)
                        extra_path = destination
                    valid, _reason = validate_xmltv_file(extra_path)
                    if not valid:
                        self._cleanup_xml(extra_path)
                        continue
                    extra_map, _extra_stats = AutoMapper(
                        sensitivity=sensitivity, overrides=load_overrides()
                    ).generate_mapping(missing, extra_path)
                    extra_map, _extra_quality = guard_mapping(extra_map, missing, extra_path, load_overrides())
                    extra_map, _removed = dedupe_mapping(extra_map)
                    duplicates_removed += _removed
                    self._log(callback, 'Kontrola dodatkowego XMLTV: przyjete %s, odrzucone %s.' % (
                        _extra_quality['accepted_refs'], _extra_quality['rejected_refs']))
                    if not extra_map:
                        self._cleanup_xml(extra_path)
                        continue
                    picon_mappings.append((extra_path, extra_map))
                    supplementary_files.append(extra_path)
                    previous_count = len(xml_refs)
                    previous_events = xml_events
                    protected_refs = set(xml_refs)
                    for epg_ref, event, epg_id in EPGParser(extra_path).iter_events(extra_map, days_ahead=days):
                        if epg_ref in protected_refs or (cfg.prefer_sat.value and epg_ref in cloned_refs):
                            continue
                        injector.add_event(epg_ref, event)
                        xml_events += 1
                        xml_refs.add(epg_ref)
                        xml_channels.add(epg_id)
                    injector.commit()
                    new_refs = len(xml_refs) - previous_count
                    new_events = xml_events - previous_events
                    source_coverage.append({'source': safe_url(secondary_url), 'kind': 'supplement',
                                            'services_with_events': new_refs, 'events': new_events})
                    self._log(callback, 'Po uzupełnieniu: +%s kanałów / +%s zdarzeń XMLTV.' % (
                        new_refs, new_events))
                except Exception as error:
                    self._log(callback, 'Uzupełniające XMLTV niedostępne: %s' % error)
                    self._cleanup_xml(extra_path)
        picon_stats = {'created': 0, 'covered': 0, 'skipped': 0}
        if cfg.picons_enabled.value:
            try:
                picon_stats = install_picons(
                    iptv, picon_mappings, sat_services=sat,
                    allow_catalog=cfg.picons_online.value, log_cb=lambda msg: self._log(callback, msg))
            except Exception as error:
                self._log(callback, 'Picony: problem podczas uzupełniania: %s' % error)
        for extra_path in supplementary_files:
            self._cleanup_xml(extra_path)

        if cfg.save_epg_cache.value:
            try:
                self.bridge.call(save_epg_cache_main, timeout=60)
                self._log(callback, "Baza EPG została zapisana na dysku przez Enigma2.")
            except Exception as error:
                self._log(callback, "Nie udało się wymusić zapisu bazy EPG: %s" % error)

        checked = {"checked": 0, "visible": 0}
        if injector.total_events > 0 and xml_refs:
            try:
                checked = self.bridge.call(verify_epg_main, sorted(xml_refs), timeout=20)
                self._log(callback, "Kontrola EPG na kanałach IPTV: widoczne %s/%s (próbka)." % (
                    checked.get('visible', 0), checked.get('checked', 0)))
                if checked.get('checked', 0) > 0 and checked.get('visible', 0) == 0:
                    self._log(callback, "UWAGA: Import zaakceptowany, lecz EPG niewidoczne w próbce. Sprawdź referencje kanałów / ustawienia image.")
            except Exception as error:
                self._log(callback, "Kontrola widoczności EPG niedostępna: %s" % error)

        duration = int(time.time() - started)
        report = {
            "source_id": source_id,
            "source_url": safe_url(source_url),
            "iptv_services": len(iptv),
            "sat_collisions_protected": len(protected),
            "iptv_reference_guard": ref_guard,
            "sat_services": len(sat),
            "skipped_nonlive": skipped,
            "sat_channels": int(sat_stats.get("channels", 0)),
            "sat_events": int(sat_stats.get("events", 0)),
            "xml_channels": len(xml_channels),
            "xml_service_refs": len(xml_refs),
            "xml_events": xml_events,
            "injector_events": injector.total_events,
            "injector_errors": injector.errors,
            "mapping": mapping_stats,
            "extra_sources": extra_sources,
            "source_coverage": source_coverage,
            "epg_autopilot": {
                "duplicate_references_removed": duplicates_removed,
                "planned_country_sources": [{"country": code, "candidates": count,
                                             "source": safe_url(url)}
                                            for code, url, count in country_plan],
                "likely_unscheduled_heuristic": likely_unscheduled_count(iptv),
                "source_count": len(source_coverage),
            },
            "picons": picon_stats,
            "verification": checked,
            "duration_seconds": duration,
            "success": bool(injector.total_events > 0),
        }
        save_report(report)
        if injector.total_events <= 0:
            update_state(
                last_result="failed", last_error="Nie zaimportowano żadnych zdarzeń EPG",
                last_source=safe_url(source_url), last_duration=duration, last_iptv=len(iptv), last_sat=len(sat),
                last_xml_channels=len(xml_channels), last_xml_events=xml_events,
                last_sat_channels=int(sat_stats.get("channels", 0)), last_inject_errors=injector.errors,
            )
            self._cleanup_xml(xml_path)
            self._log(callback, "Import zakończony bez danych: do eEPGCache nie trafiło żadne zdarzenie.")
            return False, dict(report, error="Nie zaimportowano żadnych zdarzeń EPG")
        update_state(
            last_success=int(time.time()), last_source=safe_url(source_url), last_result="success", last_error="",
            last_duration=duration, last_iptv=len(iptv), last_sat=len(sat),
            last_xml_channels=len(xml_channels), last_xml_events=xml_events,
            last_sat_channels=int(sat_stats.get("channels", 0)), last_inject_errors=injector.errors,
        )
        self._cleanup_xml(xml_path)
        self._log(callback, "GOTOWE: SAT %s kanałów | XMLTV %s kanałów / %s zdarzeń | picony +%s | czas %ss" % (
            sat_stats.get("channels", 0), len(xml_refs), xml_events, picon_stats.get('created', 0), duration))
        return True, report

    def start_picons(self, callback=None, done_callback=None):
        """Run IPTV logo repair independently of any XMLTV download."""
        if not self._acquire('picons', callback):
            return False

        def runner():
            ok, result = False, {}
            try:
                scan = scan_bouquet_services(main_call=self.bridge.call)
                services = scan.get('iptv', [])
                result = install_picons(services, [], sat_services=scan.get('sat_services', []),
                    allow_catalog=cfg.picons_online.value,
                    log_cb=lambda msg: self._log(callback, msg))
                ok = True
            except Exception as error:
                result = {'error': to_text(error)}
                self._log(callback, 'Picony IPTV: %s' % error)
            finally:
                self._release()
                if done_callback:
                    reactor.callFromThread(done_callback, ok, result, False)
        spawn_thread(runner, name='SimpleIPTVEPG-picons')
        return True

    def start_mapping(self, callback=None, done_callback=None, force=True):
        if not self._acquire("mapping", callback):
            return False

        def runner():
            ok = False
            result = {}
            xml_path = None
            try:
                scan = scan_bouquet_services(main_call=self.bridge.call)
                iptv = scan.get("iptv", [])
                if not iptv:
                    raise RuntimeError("Brak kanałów IPTV live")
                xml_path, source_id, source_url, native_channels_path = self._download_source(callback)
                if not xml_path:
                    raise RuntimeError("Nie udało się pobrać XMLTV")
                sensitivity = cfg.mapping_sensitivity.value or "balanced"
                mapper = AutoMapper(callback, sensitivity=sensitivity, overrides=load_overrides())
                sat_keys = set()
                for item in scan.get('sat_services', []):
                    fields = to_text(item.get('full_ref', '')).split(':', 10)
                    try:
                        if len(fields) == 11:
                            sat_keys.add(tuple(int(fields[i], 16) for i in (3, 4, 5, 6)))
                    except ValueError:
                        pass
                protected_iptv = []
                for item in iptv:
                    fields = to_text(item.get('full_ref', '')).split(':', 10)
                    try:
                        identity = tuple(int(fields[i], 16) for i in (3, 4, 5, 6)) if len(fields) == 11 else None
                    except ValueError:
                        identity = None
                    if not identity or identity not in sat_keys:
                        protected_iptv.append(item)
                protected_iptv, _refstats = filter_unsafe_refs(protected_iptv)
                fallback_map, stats = mapper.generate_mapping(protected_iptv, xml_path)
                fallback_map, _quality = guard_mapping(fallback_map, protected_iptv, xml_path, load_overrides())
                stats["safe_mapping"] = _quality
                native_map, native_stats = import_bmx_mapping(native_channels_path, protected_iptv)
                mapping = combine_maps(native_map, fallback_map)
                stats.update(native_stats)
                stats['xml_ids'] = len(mapping)
                if mapping:
                    self._save_mapping(mapping, scan.get("services_signature", ""), source_id, source_url, sensitivity, stats,
                                       channels_signature(native_channels_path))
                result = stats
                result["source_url"] = safe_url(source_url)
                save_report({"mapping_only": result})
                self._log(callback, "Mapowanie zakończone: %s/%s grup, XML ID: %s" % (
                    stats.get("matched_groups", 0), stats.get("groups", 0), stats.get("xml_ids", 0)))
                ok = bool(mapping)
            except Exception as error:
                result = {"error": to_text(error)}
                self._log(callback, "Błąd mapowania: %s" % error)
            finally:
                self._cleanup_xml(xml_path)
                self._release()
                if done_callback:
                    reactor.callFromThread(done_callback, ok, result, False)
        spawn_thread(runner, name="SimpleIPTVEPG-mapping")
        return True

    def start_probe(self, callback=None, done_callback=None):
        if not self._acquire("probe", callback):
            return False

        def runner():
            ok = False
            results = []
            try:
                for _source_id, url, _channels in self._selected_sources():
                    self._log(callback, "Test: %s" % safe_url(url))
                    good, message, latency = probe_url(url)
                    results.append({"url": safe_url(url), "ok": good, "message": message, "latency_ms": latency})
                    self._log(callback, "%s | %sms | %s" % ("OK" if good else "BŁĄD", latency, message))
                    if good:
                        ok = True
                        break
            finally:
                self._release()
                if done_callback:
                    reactor.callFromThread(done_callback, ok, {"sources": results}, False)
        spawn_thread(runner, name="SimpleIPTVEPG-probe")
        return True

    def start_version_check(self, callback=None, done_callback=None):
        if not self._acquire("version_check", callback):
            return False

        def runner():
            ok = False
            result = {}
            try:
                from .constants import PLUGIN_VERSION
                remote = read_remote_version()
                if not remote:
                    result = {"error": "Nie udało się odczytać wersji z repozytorium."}
                else:
                    newer = is_newer_version(remote, PLUGIN_VERSION)
                    ok = True
                    result = {"local": PLUGIN_VERSION, "remote": remote, "newer": newer}
                    self._log(callback, "Wersja lokalna: %s | repozytorium: %s" % (PLUGIN_VERSION, remote))
            except Exception as error:
                result = {"error": to_text(error)}
            finally:
                self._release()
                if done_callback:
                    reactor.callFromThread(done_callback, ok, result, False)
        spawn_thread(runner, name="SimpleIPTVEPG-version")
        return True

    def start_update(self, callback=None, done_callback=None):
        if not self._acquire("update", callback):
            return False

        def runner():
            ok = False
            result = {}
            try:
                ok, message = safe_update_plugin(log_cb=callback)
                result = {"message": message}
            except Exception as error:
                result = {"error": to_text(error)}
            finally:
                self._release()
                if done_callback:
                    reactor.callFromThread(done_callback, ok, result, False)
        spawn_thread(runner, name="SimpleIPTVEPG-update")
        return True

    def clear_mapping_cache(self):
        removed = 0
        for path in [MAPPING_FILE, REPORT_FILE]:
            try:
                if os.path.exists(path):
                    os.remove(path)
                    removed += 1
            except Exception:
                pass
        return removed

    def clear_temp(self):
        removed = 0
        try:
            if os.path.isdir(TMP_DIR):
                for name in os.listdir(TMP_DIR):
                    path = os.path.join(TMP_DIR, name)
                    if os.path.isfile(path):
                        try:
                            os.remove(path)
                            removed += 1
                        except Exception:
                            pass
        except Exception:
            pass
        return removed


GLOBAL_WORKER = EPGWorker()
