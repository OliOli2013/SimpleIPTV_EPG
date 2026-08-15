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
    read_remote_version, is_newer_version,
    scan_bouquet_services, source_fingerprint, validate_xmltv_file,
)
from .logger import log_message
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
        if source_id == "CUSTOM":
            url = to_text(cfg.custom_url.value).strip()
            if url.startswith("http://") or url.startswith("https://"):
                return [(source_id, url)]
            return []
        source = SOURCE_MAP.get(source_id) or SOURCE_MAP.get("AUTO_PL")
        return [(source_id, url) for url in (source.get("urls") or [])]

    def _download_source(self, callback):
        sources = self._selected_sources()
        if not sources:
            self._log(callback, "Nie ustawiono prawidłowego źródła XMLTV.")
            return None, None, None
        ensure_dir(TMP_DIR)
        for index, (source_id, url) in enumerate(sources):
            suffix = ".xml.gz" if url.lower().endswith(".gz") else ".xml"
            target = os.path.join(TMP_DIR, "guide-%s%s" % (source_fingerprint(url), suffix))
            self._log(callback, "Źródło %s/%s: %s" % (index + 1, len(sources), url))
            if not download_file(url, target, timeout=240, retries=2, log_cb=callback):
                self._log(callback, "Pobieranie nie powiodło się – próbuję kolejnego źródła.")
                continue
            valid, reason = validate_xmltv_file(target)
            if valid:
                self._log(callback, "XMLTV poprawny: %s" % url)
                return target, source_id, url
            self._log(callback, "Odrzucono nieprawidłowy XMLTV (%s)." % reason)
            try:
                os.remove(target)
            except Exception:
                pass
        return None, None, None

    def _mapping_cache(self, signature, source_url, sensitivity):
        payload = load_json(MAPPING_FILE, {})
        if not isinstance(payload, dict):
            return None, {}
        meta = payload.get("_meta") if isinstance(payload.get("_meta"), dict) else {}
        mapping = payload.get("mapping") if isinstance(payload.get("mapping"), dict) else None
        if not mapping:
            return None, meta
        if meta.get("services_signature") != signature:
            return None, meta
        if meta.get("source_url") != source_url:
            return None, meta
        if meta.get("sensitivity") != sensitivity:
            return None, meta
        return mapping, meta

    def _save_mapping(self, mapping, signature, source_id, source_url, sensitivity, stats):
        payload = {
            "_meta": {
                "services_signature": signature,
                "source_id": source_id,
                "source_url": source_url,
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
        self._log(callback, "Wykryto IPTV live: %s | SAT: %s | pominięte VOD/serie: %s" % (len(iptv), len(sat), skipped))
        if not iptv:
            update_state(last_result="failed", last_error="Brak kanałów IPTV live")
            return False, {"error": "Brak kanałów IPTV live"}

        xml_path, source_id, source_url = self._download_source(callback)
        if not xml_path:
            update_state(last_result="failed", last_error="Nie udało się pobrać prawidłowego XMLTV")
            return False, {"error": "Nie udało się pobrać prawidłowego XMLTV"}

        days = int(cfg.import_days.value or "5")
        sensitivity = cfg.mapping_sensitivity.value or "balanced"
        mapping = None
        mapping_stats = {}
        if not force_mapping:
            mapping, _meta = self._mapping_cache(signature, source_url, sensitivity)
        if mapping:
            self._log(callback, "Używam poprawnego cache mapowania dla tego źródła i aktualnych bukietów.")
            mapping_stats = {"groups": len(iptv), "matched_groups": -1, "xml_ids": len(mapping), "cached": True}
        else:
            self._log(callback, "Budowanie inteligentnego mapowania XMLTV...")
            mapper = AutoMapper(callback, sensitivity=sensitivity, overrides=load_overrides())
            mapping, mapping_stats = mapper.generate_mapping(iptv, xml_path)
            if mapping:
                self._save_mapping(mapping, signature, source_id, source_url, sensitivity, mapping_stats)
            self._log(callback, "Mapowanie: %s XML ID | niedopasowane: %s | niejednoznaczne: %s" % (
                len(mapping or {}), mapping_stats.get("unmatched", 0), mapping_stats.get("ambiguous", 0)))

        injector = SafeEPGInjector(self.bridge.call)
        cloned_refs = set()
        sat_stats = {"channels": 0, "events": 0}
        if cfg.clone_sat.value and sat:
            self._log(callback, "Kopiowanie pewnych dopasowań EPG z SAT do IPTV...")
            sat_stats = clone_sat_to_iptv(injector, iptv, sat, days_ahead=days, main_call=self.bridge.call, log_cb=callback)
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

        if cfg.save_epg_cache.value:
            try:
                self.bridge.call(save_epg_cache_main, timeout=60)
                self._log(callback, "Baza EPG została zapisana na dysku przez Enigma2.")
            except Exception as error:
                self._log(callback, "Nie udało się wymusić zapisu bazy EPG: %s" % error)

        duration = int(time.time() - started)
        report = {
            "source_id": source_id,
            "source_url": source_url,
            "iptv_services": len(iptv),
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
            "duration_seconds": duration,
            "success": bool(injector.total_events > 0),
        }
        save_report(report)
        if injector.total_events <= 0:
            update_state(
                last_result="failed", last_error="Nie zaimportowano żadnych zdarzeń EPG",
                last_source=source_url, last_duration=duration, last_iptv=len(iptv), last_sat=len(sat),
                last_xml_channels=len(xml_channels), last_xml_events=xml_events,
                last_sat_channels=int(sat_stats.get("channels", 0)), last_inject_errors=injector.errors,
            )
            self._cleanup_xml(xml_path)
            self._log(callback, "Import zakończony bez danych: do eEPGCache nie trafiło żadne zdarzenie.")
            return False, dict(report, error="Nie zaimportowano żadnych zdarzeń EPG")
        update_state(
            last_success=int(time.time()), last_source=source_url, last_result="success", last_error="",
            last_duration=duration, last_iptv=len(iptv), last_sat=len(sat),
            last_xml_channels=len(xml_channels), last_xml_events=xml_events,
            last_sat_channels=int(sat_stats.get("channels", 0)), last_inject_errors=injector.errors,
        )
        self._cleanup_xml(xml_path)
        self._log(callback, "GOTOWE: SAT %s kanałów | XMLTV %s kanałów / %s zdarzeń | czas %ss" % (
            sat_stats.get("channels", 0), len(xml_refs), xml_events, duration))
        return True, report

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
                xml_path, source_id, source_url = self._download_source(callback)
                if not xml_path:
                    raise RuntimeError("Nie udało się pobrać XMLTV")
                sensitivity = cfg.mapping_sensitivity.value or "balanced"
                mapper = AutoMapper(callback, sensitivity=sensitivity, overrides=load_overrides())
                mapping, stats = mapper.generate_mapping(iptv, xml_path)
                if mapping:
                    self._save_mapping(mapping, scan.get("services_signature", ""), source_id, source_url, sensitivity, stats)
                result = stats
                result["source_url"] = source_url
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
                for _source_id, url in self._selected_sources():
                    self._log(callback, "Test: %s" % url)
                    good, message, latency = probe_url(url)
                    results.append({"url": url, "ok": good, "message": message, "latency_ms": latency})
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
