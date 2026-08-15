# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function

import time

from Plugins.Plugin import PluginDescriptor
from Screens.MessageBox import MessageBox
from twisted.internet import reactor

from .constants import PLUGIN_BUILD, PLUGIN_TITLE, PLUGIN_VERSION
from .logger import log_message
from .screens import SimpleIPTVEPGMain, set_active_session
from .settings import cfg
from .storage import load_state
from .worker import GLOBAL_WORKER

SCHEDULER_CALL = None
SCHEDULER_STARTED = False
ACTIVE_SESSION = None


def main(session, **kwargs):
    global ACTIVE_SESSION
    ACTIVE_SESSION = session
    set_active_session(session)
    session.open(SimpleIPTVEPGMain)


def _auto_done(ok, result, silent):
    if not cfg.notify_done.value or ACTIVE_SESSION is None:
        return
    if ok:
        message = "Automatyczny import EPG zakończony. XMLTV: %s kanałów / %s zdarzeń, SAT: %s kanałów." % (
            result.get("xml_service_refs", 0), result.get("xml_events", 0), result.get("sat_channels", 0))
    else:
        message = "Automatyczny import EPG nie powiódł się: %s" % result.get("error", "sprawdź log")
    try:
        ACTIVE_SESSION.open(MessageBox, message, MessageBox.TYPE_INFO, timeout=8)
    except Exception:
        pass


def _schedule_next(seconds=1800):
    global SCHEDULER_CALL
    try:
        if SCHEDULER_CALL is not None and SCHEDULER_CALL.active():
            SCHEDULER_CALL.cancel()
    except Exception:
        pass
    SCHEDULER_CALL = reactor.callLater(int(seconds), _scheduler_tick)


def _scheduler_tick():
    try:
        interval = int(cfg.auto_interval.value or "0")
    except Exception:
        interval = 0
    if interval <= 0:
        _schedule_next(1800)
        return

    now = int(time.time())
    state = load_state()
    last_success = int(state.get("last_success") or 0)
    last_attempt = int(state.get("last_attempt") or 0)
    due = (not last_success) or ((now - last_success) >= interval * 3600)
    # Nie zapętlamy nieudanych prób co 30 minut. Po błędzie czekamy min. 3h.
    retry_allowed = (not last_attempt) or ((now - last_attempt) >= min(interval * 3600, 3 * 3600))

    if due and retry_allowed and not GLOBAL_WORKER.running:
        log_message("AUTO: uruchamiam zaplanowany import EPG.")
        GLOBAL_WORKER.start_import(callback=None, done_callback=_auto_done, silent=True, force_mapping=False)
    _schedule_next(1800)


def session_start(reason, session=None, **kwargs):
    global ACTIVE_SESSION, SCHEDULER_STARTED, SCHEDULER_CALL
    if reason != 0:
        return
    if session is not None:
        ACTIVE_SESSION = session
        set_active_session(session)
    if SCHEDULER_STARTED:
        return
    SCHEDULER_STARTED = True
    try:
        delay = int(cfg.boot_delay.value or "120")
    except Exception:
        delay = 120
    SCHEDULER_CALL = reactor.callLater(max(20, delay), _scheduler_tick)
    log_message("Scheduler EPG uruchomiony; pierwszy test za %ss." % max(20, delay))


def Plugins(**kwargs):
    description = "AIO XMLTV + SAT EPG importer dla kanałów IPTV"
    return [
        PluginDescriptor(
            name="%s %s %s" % (PLUGIN_TITLE, PLUGIN_VERSION, PLUGIN_BUILD),
            description=description,
            where=PluginDescriptor.WHERE_PLUGINMENU,
            icon="plugin.png",
            fnc=main,
        ),
        PluginDescriptor(
            where=PluginDescriptor.WHERE_SESSIONSTART,
            fnc=session_start,
        ),
    ]
