# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function

import io
import os
import subprocess
import sys
import threading

PY2 = sys.version_info[0] < 3
PY3 = not PY2

try:
    text_type = unicode
    binary_type = str
except NameError:
    text_type = str
    binary_type = bytes

try:
    from urllib.parse import unquote, urlparse
    from urllib.request import Request, urlopen
except ImportError:
    from urllib import unquote
    from urlparse import urlparse
    from urllib2 import Request, urlopen


def to_text(value, encoding="utf-8"):
    if value is None:
        return u""
    if isinstance(value, text_type):
        return value
    if isinstance(value, binary_type):
        try:
            return value.decode(encoding, "ignore")
        except Exception:
            pass
    try:
        return text_type(value)
    except Exception:
        return u""


def to_bytes(value, encoding="utf-8"):
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return to_text(value).encode(encoding, "ignore")


def ensure_dir(path):
    if not path:
        return
    if not os.path.isdir(path):
        try:
            os.makedirs(path)
        except OSError:
            if not os.path.isdir(path):
                raise


def command_exists(name):
    paths = os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin").split(os.pathsep)
    for folder in paths:
        candidate = os.path.join(folder, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def run_command(command, timeout=120):
    """Return (returncode, combined output). Python 2/3 compatible."""
    process = None
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        timer = None
        killed = [False]

        def kill_process():
            if process.poll() is None:
                killed[0] = True
                try:
                    process.kill()
                except Exception:
                    pass

        if timeout:
            timer = threading.Timer(float(timeout), kill_process)
            timer.daemon = True
            timer.start()
        output = process.communicate()[0] or b""
        if timer:
            timer.cancel()
        code = process.returncode
        if killed[0] and code == 0:
            code = 124
        return code, to_text(output)
    except Exception as error:
        try:
            if process and process.poll() is None:
                process.kill()
        except Exception:
            pass
        return 127, to_text(error)


def spawn_thread(target, args=None, kwargs=None, name=None):
    thread = threading.Thread(target=target, args=args or (), kwargs=kwargs or {}, name=name)
    thread.daemon = True
    thread.start()
    return thread


def io_open(path, mode="r"):
    if "b" in mode:
        return open(path, mode)
    return io.open(path, mode, encoding="utf-8", errors="ignore")
