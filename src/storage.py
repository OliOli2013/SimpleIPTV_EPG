# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function

import json
import os
import shutil
import time

from .compat import ensure_dir, io_open
from .constants import STATE_FILE, REPORT_FILE


def load_json(path, default=None):
    if not path or not os.path.exists(path):
        return {} if default is None else default
    try:
        with io_open(path, "r") as handle:
            data = json.load(handle)
        return data
    except Exception:
        return {} if default is None else default


def atomic_write_json(payload, path):
    directory = os.path.dirname(path) or "/tmp"
    ensure_dir(directory)
    temp = path + ".tmp"
    try:
        with io_open(temp, "w") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        try:
            os.rename(temp, path)
        except Exception:
            shutil.move(temp, path)
        return True
    except Exception:
        try:
            if os.path.exists(temp):
                os.remove(temp)
        except Exception:
            pass
        return False


def load_state():
    data = load_json(STATE_FILE, {})
    return data if isinstance(data, dict) else {}


def update_state(**values):
    data = load_state()
    data.update(values)
    data["state_saved_at"] = int(time.time())
    atomic_write_json(data, STATE_FILE)
    return data


def save_report(report):
    if not isinstance(report, dict):
        return False
    report = dict(report)
    report["saved_at"] = int(time.time())
    return atomic_write_json(report, REPORT_FILE)
