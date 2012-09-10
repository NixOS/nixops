# -*- coding: utf-8 -*-

import os
import sys
import time
import json
import copy
import fcntl
import base64
import socket
import struct

devnull = open(os.devnull, 'rw')

def check_wait(test, initial=10, factor=1, max_tries=60):
    """Call function ‘test’ periodically until it returns True or a timeout occurs."""
    wait = initial
    tries = 0
    while tries < max_tries and not test():
        time.sleep(wait)
        wait = wait * factor
        tries = tries + 1
        if tries == max_tries:
            raise Exception("operation timed out")
    return True

def generate_random_string(length=256):
    """Generate a base-64 encoded cryptographically strong random string."""
    f = open("/dev/urandom", "r")
    s = f.read(length)
    assert len(s) == length
    return base64.b64encode(s)

def make_non_blocking(fd):
    fcntl.fcntl(fd, fcntl.F_SETFL, fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK)

def ping_tcp_port(ip, port, timeout=1, ensure_timeout=False):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
    try:
        s.connect((ip, port))
    except socket.timeout:
        return False
    except:
        # FIXME: check that we got a transient error (like connection
        # refused or no route to host). For any other error, throw an
        # exception.
        if ensure_timeout: time.sleep(timeout)
        return False
    s.shutdown(socket.SHUT_RDWR)
    return True

def wait_for_tcp_port(ip, port, timeout=-1, open=True, callback=None):
    """Wait until the specified TCP port is open or closed."""
    n = 0
    while True:
        if ping_tcp_port(ip, port, ensure_timeout=True) == open: return True
        if not open: time.sleep(1)
        n = n + 1
        if timeout != -1 and n >= timeout: break
        if callback: callback()
    raise Error("timed out waiting for port {0} on ‘{1}’".format(port, ip))

def ansi_warn(s, outfile=sys.stderr):
    return "\033[1;31m" + s + "\033[0m" if outfile.isatty() else s

def abs_nix_path(x):
    xs = x.split('=', 1)
    if len(xs) == 1: return os.path.abspath(x)
    return xs[0] + '=' + os.path.abspath(xs[1])

undefined = object()

def attr_property(name, default, type=str):
    """Define a property that corresponds to a value in the Charon state file."""
    def get(self):
        s = self._get_attr(name, default)
        if s == undefined:
            if default != undefined: return copy.deepcopy(default)
            raise Exception("deployment attribute ‘{0}’ missing from state file".format(name))
        if s == None: return None
        elif type is str: return s
        elif type is int: return int(s)
        elif type is bool: return True if s == "1" else False
        elif type is 'json': return json.loads(s)
        else: assert False
    def set(self, x):
        if x == default: self._del_attr(name)
        elif type is 'json': self._set_attr(name, json.dumps(x))
        else: self._set_attr(name, x)
    return property(get, set)
