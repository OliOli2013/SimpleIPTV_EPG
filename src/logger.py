# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function

import datetime
import os

from .compat import ensure_dir, io_open, to_text
from .constants import LOG_FILE


def log_message(message):
    try:
        ensure_dir(os.path.dirname(LOG_FILE))
        with io_open(LOG_FILE, "a") as handle:
            handle.write(u"[%s] %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), to_text(message)))
    except Exception:
        pass


def clear_log():
    try:
        if os.path.exists(LOG_FILE):
            os.remove(LOG_FILE)
        return True
    except Exception:
        return False
