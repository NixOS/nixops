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
import shutil
import tempfile
import subprocess
import logging
from StringIO import StringIO

devnull = open(os.devnull, 'rw')


def check_wait(test, initial=10, factor=1, max_tries=60, exception=True):
    """Call function ‘test’ periodically until it returns True or a timeout occurs."""
    wait = initial
    tries = 0
    while tries < max_tries and not test():
        time.sleep(wait)
        wait = wait * factor
        tries = tries + 1
        if tries == max_tries:
            if exception: raise Exception("operation timed out")
            return False
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
    raise Exception("timed out waiting for port {0} on ‘{1}’".format(port, ip))


def ansi_warn(s, outfile=sys.stderr):
    return "\033[1;31m" + s + "\033[0m" if outfile.isatty() else s


def ansi_success(s, outfile=sys.stderr):
    return "\033[1;32m" + s + "\033[0m" if outfile.isatty() else s


def abs_nix_path(x):
    xs = x.split('=', 1)
    if len(xs) == 1: return os.path.abspath(x)
    return xs[0] + '=' + os.path.abspath(xs[1])


def make_nix_string(s):
    t = '"'
    for c in s:
        if c == '\\': t += "\\\\"
        elif c == '\n': t += "\\n"
        elif c == '\r': t += "\\r"
        elif c == '\t': t += "\\t"
        elif c == '"': t += '\\"'
        else: t += c
    t += '"'
    return t


undefined = object()

def attr_property(name, default, type=str):
    """Define a property that corresponds to a value in the NixOps state file."""
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


def create_key_pair(key_name="NixOps auto-generated key", type="dsa"):
    key_dir = tempfile.mkdtemp(prefix="nixops-tmp")
    res = subprocess.call(["ssh-keygen", "-t", type, "-f", key_dir + "/key", "-N", '', "-C", key_name],
                          stdout=devnull)
    if res != 0: raise Exception("unable to generate an SSH key")
    f = open(key_dir + "/key"); private = f.read(); f.close()
    f = open(key_dir + "/key.pub"); public = f.read().rstrip(); f.close()
    shutil.rmtree(key_dir)
    return (private, public)


class SelfDeletingDir(str):
    def __del__(self):
        shutil.rmtree(self)
        try:
            super(SelfDeletingDir,self).__del__()
        except AttributeError:
            pass

class TeeStderr(StringIO):
    stderr = None
    def __init__(self):
        StringIO.__init__(self)
        self.stderr = sys.stderr
        self.logger = logging.getLogger('root')
        sys.stderr = self
    def __del__(self):
        sys.stderr = self.stderr
    def write(self, data):
        self.stderr.write(data)
        for l in data.split('\n'):
            self.logger.warning(l)
    def fileno(self):
        return self.stderr.fileno()
    def isatty(self):
        return self.stderr.isatty()

class TeeStdout(StringIO):
    stdout = None
    def __init__(self):
        StringIO.__init__(self)
        self.stdout = sys.stdout
        self.logger = logging.getLogger('root')
        sys.stdout = self
    def __del__(self):
        sys.stdout = self.stdout
    def write(self, data):
        self.stdout.write(data)
        for l in data.split('\n'):
            self.logger.info(l)
    def fileno(self):
        return self.stdout.fileno()
    def isatty(self):
        return self.stdout.isatty()


# Borrowed from http://stackoverflow.com/questions/377017/test-if-executable-exists-in-python.
def which(program):
    import os
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    raise Exception("program ‘{0}’ not found in \$PATH".format(program))
