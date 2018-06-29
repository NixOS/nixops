# -*- coding: utf-8 -*-

import os
import sys
import time
import json
import copy
import fcntl
import base64
import select
import socket
import struct
import shutil
import tempfile
import subprocess
import logging
import atexit
import re
from StringIO import StringIO

devnull = open(os.devnull, 'rw')


def check_wait(test, initial=10, factor=1, max_tries=60, exception=True):
    """Call function ‘test’ periodically until it returns True or a timeout occurs."""
    wait = initial
    tries = 0
    while tries < max_tries and not test():
        wait = wait * factor
        tries = tries + 1
        if tries == max_tries:
            if exception: raise Exception("operation timed out")
            return False
        time.sleep(wait)
    return True


class CommandFailed(Exception):
    def __init__(self, message, exitcode):
        self.message = message
        self.exitcode = exitcode

    def __str__(self):
        return "{0} (exit code {1})".format(self.message, self.exitcode)


def logged_exec(command, logger, check=True, capture_stdout=False, stdin=None,
                stdin_string=None, env=None):
    """
    Execute a command with logging using the specified logger.

    The command itself has to be an iterable of strings, just like
    subprocess.Popen without shell=True. Keywords stdin and env have the same
    functionality as well.

    When calling with capture_stdout=True, a string is returned, which contains
    everything the program wrote to stdout.

    When calling with check=False, the return code isn't checked and the
    function will return an integer which represents the return code of the
    program, otherwise a CommandFailed exception is thrown.
    """
    if stdin_string is not None:
        stdin = subprocess.PIPE
    elif stdin is None:
        stdin = devnull

    if capture_stdout:
        process = subprocess.Popen(command, env=env, stdin=stdin,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        fds = [process.stdout, process.stderr]
        log_fd = process.stderr
    else:
        process = subprocess.Popen(command, env=env, stdin=stdin,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
        fds = [process.stdout]
        log_fd = process.stdout

    # FIXME: this can deadlock if stdin_string doesn't fit in the
    # kernel pipe buffer.
    if stdin_string is not None:
        # PIPE_BUF is not the size of the kernel pipe buffer (see
        # https://unix.stackexchange.com/questions/11946/how-big-is-the-pipe-buffer)
        # but if something fits in PIPE_BUF, it'll fit in the kernel pipe
        # buffer.
        # So we use PIPE_BUF as the threshold to emit a warning,
        # so that if the deadlock described above does happen,
        # the user at least knows what the cause is.
        if len(stdin_string) > select.PIPE_BUF:
            sys.stderr.write(
                ("Warning: Feeding more than PIPE_BUF = {} bytes ({})" +
                " via stdin to a subprocess. This may deadlock." +
                " Please report it as a bug if you see it happen," +
                " at https://github.com/NixOS/nixops/issues/800\n"
                ).format(select.PIPE_BUF, len(stdin_string)))

        process.stdin.write(stdin_string)
        process.stdin.close()

    for fd in fds:
        make_non_blocking(fd)

    at_new_line = True
    stdout = ""

    while len(fds) > 0:
        # The timeout/poll is to deal with processes (like
        # VBoxManage) that start children that go into the
        # background but keep the parent's stdout/stderr open,
        # preventing an EOF.  FIXME: Would be better to catch
        # SIGCHLD.
        (r, w, x) = select.select(fds, [], [], 1)
        if len(r) == 0 and process.poll() is not None:
            break
        if capture_stdout and process.stdout in r:
            data = process.stdout.read()
            if data == "":
                fds.remove(process.stdout)
            else:
                stdout += data
        if log_fd in r:
            data = log_fd.read()
            if data == "":
                if not at_new_line:
                    logger.log_end("")
                fds.remove(log_fd)
            else:
                start = 0
                while start < len(data):
                    end = data.find('\n', start)
                    if end == -1:
                        logger.log_start(data[start:])
                        at_new_line = False
                    else:
                        s = data[start:end]
                        if at_new_line:
                            logger.log(s)
                        else:
                            logger.log_end(s)
                        at_new_line = True
                    if end == -1:
                        break
                    start = end + 1

    res = process.wait()

    if check and res != 0:
        msg = "command ‘{0}’ failed on machine ‘{1}’"
        err = msg.format(command, logger.machine_name)
        raise CommandFailed(err, res)

    return stdout if capture_stdout else res


def generate_random_string(length=256):
    """Generate a base-64 encoded cryptographically strong random string."""
    s = os.urandom(length)
    assert len(s) == length
    return base64.b64encode(s)


def make_non_blocking(fd):
    fcntl.fcntl(fd, fcntl.F_SETFL, fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK)


def ping_tcp_port(host, port, timeout=1, ensure_timeout=False):
    """"
    Return to True or False depending on being able to connect the specified host and port.
    Raises exceptions which are not related to opening a socket to the target host.
    """
    infos = socket.getaddrinfo(host, port, 0, 0, socket.IPPROTO_TCP)
    for info in infos:
        s = socket.socket(info[0], info[1])
        s.settimeout(timeout)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
        try:
            s.connect(info[4])
        except socket.timeout:
            # try next address
            continue
        except EnvironmentError:
            # Reset, Refused, Aborted, No route to host
            if ensure_timeout: time.sleep(timeout)
            # continue with the next address
            continue
        except:
            raise
        else:
            s.shutdown(socket.SHUT_RDWR)
            return True
    return False


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


def ansi_highlight(s, outfile=sys.stderr):
    return "\033[1;35m" + s + "\033[0m" if outfile.isatty() else s


def ansi_warn(s, outfile=sys.stderr):
    return "\033[1;33m" + s + "\033[0m" if outfile.isatty() else s


def ansi_error(s, outfile=sys.stderr):
    return "\033[1;31m" + s + "\033[0m" if outfile.isatty() else s


def ansi_success(s, outfile=sys.stderr):
    return "\033[1;32m" + s + "\033[0m" if outfile.isatty() else s


def _maybe_abspath(s):
    if s.startswith("http://") or s.startswith("https://") or s.startswith("file://") or s.startswith("channel:"):
        return s
    return os.path.abspath(s)


def abs_nix_path(x):
    xs = x.split('=', 1)
    if len(xs) == 1: return _maybe_abspath(x)
    return xs[0] + '=' + _maybe_abspath(xs[1])


class Undefined:
    pass

undefined = Undefined()


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


def create_key_pair(key_name="NixOps auto-generated key", type="ed25519"):
    key_dir = tempfile.mkdtemp(prefix="nixops-key-tmp")
    res = subprocess.call(["ssh-keygen", "-t", type, "-f", key_dir + "/key", "-N", '', "-C", key_name],
                          stdout=devnull)
    if res != 0: raise Exception("unable to generate an SSH key")
    f = open(key_dir + "/key"); private = f.read(); f.close()
    f = open(key_dir + "/key.pub"); public = f.read().rstrip(); f.close()
    shutil.rmtree(key_dir)
    return (private, public)


class SelfDeletingDir(str):
    def __init__(self, s):
        str.__init__(s)
        atexit.register(self._delete)
    def _delete(self):
        shutil.rmtree(self)


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


def enum(**enums):
    return type('Enum', (), enums)


def write_file(path, contents):
    f = open(path, "w")
    f.write(contents)
    f.close()


def xml_expr_to_python(node):
    if node.tag == "attrs":
        res = {}
        for attr in node.findall("attr"):
            if attr.get("name") != "_module":
                res[attr.get("name")] = xml_expr_to_python(attr.find("*"))
        return res

    elif node.tag == "list":
        res = []
        for elem in node.findall("*"):
            res.append(xml_expr_to_python(elem))
        return res

    elif node.tag == "string":
        return node.get("value")

    elif node.tag == "path":
        return node.get("value")

    elif node.tag == "bool":
        return node.get("value") == "true"

    elif node.tag == "int":
        return int(node.get("value"))

    elif node.tag == "null":
        return None

    elif node.tag == "derivation":
        return {"drvPath": node.get("drvPath/"), "outPath": node.get("outPath")}

    raise Exception("cannot convert XML output of nix-instantiate to Python: Unknown tag "+node.tag)


def parse_nixos_version(s):
    """Split a NixOS version string into a list of components."""
    return s.split(".")

# sd -> sd
# xvd -> sd
# nvme -> sd
def device_name_to_boto_expected(string):
    """Transfoms device name to name, that boto expects."""
    m = re.search('(.*)\/nvme(\d+)n1p?(\d+)?', string)
    if m != None:
        device = m.group(2)
        device_ = int(device) - 1
        device_transformed = chr(ord('f') + device_)

        partition = m.group(3) or ''

        return "{0}/sd{1}{2}".format(m.group(1), device_transformed, partition)
    else:
        return string.replace("/dev/xvd", "/dev/sd")

# sd -> sd
# xvd -> sd
# nvme -> nvme
def device_name_user_entered_to_stored(string):
    return string.replace("/dev/xvd", "/dev/sd")

# sd -> xvd
# xvd -> xvd
# nvme -> nvme
def device_name_stored_to_real(string):
    return string.replace("/dev/sd", "/dev/xvd")
