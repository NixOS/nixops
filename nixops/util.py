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
from typing import Callable, List, Optional, Any, IO, Union, Mapping, TextIO, Tuple

# the following ansi_ imports are for backwards compatability. They
# would belong fine in this util.py, but having them in util.py
# causes an import cycle with types.
from nixops.ansi import ansi_warn, ansi_error, ansi_success, ansi_highlight
from nixops.logger import MachineLogger
from io import StringIO


devnull = open(os.devnull, "r+")


def check_wait(
    test: Callable[[], bool],
    initial: int = 10,
    factor: int = 1,
    max_tries: int = 60,
    exception: bool = True,
) -> bool:
    """Call function ‘test’ periodically until it returns True or a timeout occurs."""
    wait = initial
    tries = 0
    while tries < max_tries and not test():
        wait = wait * factor
        tries = tries + 1
        if tries == max_tries:
            if exception:
                raise Exception("operation timed out")
            return False
        time.sleep(wait)
    return True


class CommandFailed(Exception):
    def __init__(self, message: str, exitcode: int) -> None:
        self.message = message
        self.exitcode = exitcode

    def __str__(self) -> str:
        return "{0} (exit code {1})".format(self.message, self.exitcode)


def logged_exec(
    command: List[str],
    logger: MachineLogger,
    check: bool = True,
    capture_stdout: bool = False,
    stdin: Optional[IO[Any]] = None,
    stdin_string: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    preexec_fn: Optional[Callable[[], Any]] = None,
) -> Union[str, int]:
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
    passed_stdin: Union[int, IO[Any]]

    if stdin_string is not None:
        passed_stdin = subprocess.PIPE
    elif stdin is not None:
        passed_stdin = stdin
    else:
        passed_stdin = devnull

    fds: List[IO[str]] = []
    if capture_stdout:
        process = subprocess.Popen(
            command,
            env=env,
            stdin=passed_stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=preexec_fn,
            text=True,
        )
        fds = [fd for fd in [process.stdout, process.stderr] if fd]
        log_fd_opt = process.stderr
    else:
        process = subprocess.Popen(
            command,
            env=env,
            stdin=passed_stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=preexec_fn,
            text=True,
        )
        if process.stdout:
            fds = [process.stdout]
        log_fd_opt = process.stdout

    if process.stdin is None:
        raise ValueError("process.stdin was None")
    process_stdin: IO[str] = process.stdin

    if process.stdout is None:
        raise ValueError("process.stdout was None")
    process_stdout: IO[str] = process.stdout

    if log_fd_opt is None:
        raise ValueError("log_fd was None")
    log_fd: IO[str] = log_fd_opt

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
                (
                    "Warning: Feeding more than PIPE_BUF = {} bytes ({})"
                    + " via stdin to a subprocess. This may deadlock."
                    + " Please report it as a bug if you see it happen,"
                    + " at https://github.com/NixOS/nixops/issues/800\n"
                ).format(select.PIPE_BUF, len(stdin_string))
            )

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
                    end = data.find("\n", start)
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


def generate_random_string(length=256) -> str:
    """Generate a base-64 encoded cryptographically strong random string."""
    s = os.urandom(length)
    assert len(s) == length
    return base64.b64encode(s).decode()


def make_non_blocking(fd: IO[Any]) -> None:
    fcntl.fcntl(fd, fcntl.F_SETFL, fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK)


def ping_tcp_port(
    host: str, port: int, timeout: int = 1, ensure_timeout: bool = False
) -> bool:
    """"
    Return to True or False depending on being able to connect the specified host and port.
    Raises exceptions which are not related to opening a socket to the target host.
    """
    infos = socket.getaddrinfo(host, port, 0, 0, socket.IPPROTO_TCP)
    for info in infos:
        s = socket.socket(info[0], info[1])
        s.settimeout(timeout)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        try:
            s.connect(info[4])
        except socket.timeout:
            # try next address
            continue
        except EnvironmentError:
            # Reset, Refused, Aborted, No route to host
            if ensure_timeout:
                time.sleep(timeout)
            # continue with the next address
            continue
        except:
            raise
        else:
            s.shutdown(socket.SHUT_RDWR)
            return True
    return False


def wait_for_tcp_port(
    ip: str,
    port: int,
    timeout: int = -1,
    open: bool = True,
    callback: Optional[Callable[[], Any]] = None,
) -> bool:
    """Wait until the specified TCP port is open or closed."""
    n = 0
    while True:
        if ping_tcp_port(ip, port, ensure_timeout=True) == open:
            return True
        if not open:
            time.sleep(1)
        n = n + 1
        if timeout != -1 and n >= timeout:
            break
        if callback:
            callback()
    raise Exception("timed out waiting for port {0} on ‘{1}’".format(port, ip))


def _maybe_abspath(s: str) -> str:
    if (
        s.startswith("http://")
        or s.startswith("https://")
        or s.startswith("file://")
        or s.startswith("channel:")
    ):
        return s
    return os.path.abspath(s)


def abs_nix_path(x: str) -> str:
    xs = x.split("=", 1)
    if len(xs) == 1:
        return _maybe_abspath(x)
    return xs[0] + "=" + _maybe_abspath(xs[1])


class Undefined:
    pass


undefined = Undefined()


def attr_property(name: str, default: Any, type: Optional[Any] = str) -> Any:
    """Define a property that corresponds to a value in the NixOps state file."""

    def get(self) -> Any:
        s: Any = self._get_attr(name, default)
        if s == undefined:
            if default != undefined:
                return copy.deepcopy(default)
            raise Exception(
                "deployment attribute ‘{0}’ missing from state file".format(name)
            )
        if s == None:
            return None
        elif type is str:
            return s
        elif type is int:
            return int(s)
        elif type is bool:
            return True if s == "1" else False
        elif type is "json":
            return json.loads(s)
        else:
            assert False

    def set(self, x: Any) -> None:
        if x == default:
            self._del_attr(name)
        elif type is "json":
            self._set_attr(name, json.dumps(x))
        else:
            self._set_attr(name, x)

    return property(get, set)


def create_key_pair(
    key_name="NixOps auto-generated key", type="ed25519"
) -> Tuple[str, str]:
    key_dir = tempfile.mkdtemp(prefix="nixops-key-tmp")
    res = subprocess.call(
        ["ssh-keygen", "-t", type, "-f", key_dir + "/key", "-N", "", "-C", key_name],
        stdout=devnull,
    )
    if res != 0:
        raise Exception("unable to generate an SSH key")
    with open(key_dir + "/key") as f:
        private = f.read()
    with open(key_dir + "/key.pub") as f:
        public = f.read().rstrip()
    shutil.rmtree(key_dir)
    return (private, public)


class SelfDeletingDir(str):
    def __init__(self, s: str) -> None:
        str.__init__(s)
        atexit.register(self._delete)

    def _delete(self) -> None:
        shutil.rmtree(self)


class TeeStderr(StringIO):
    stderr: TextIO

    def __init__(self) -> None:
        StringIO.__init__(self)
        self.stderr = sys.stderr
        self.logger = logging.getLogger("root")
        sys.stderr = self

    def __del__(self) -> None:
        sys.stderr = self.stderr

    def write(self, data) -> int:
        ret = self.stderr.write(data)
        for l in data.split("\n"):
            self.logger.warning(l)
        return ret

    def fileno(self) -> int:
        return self.stderr.fileno()

    def isatty(self) -> bool:
        return self.stderr.isatty()

    def flush(self) -> None:
        return self.stderr.flush()


class TeeStdout(StringIO):
    stdout: TextIO

    def __init__(self) -> None:
        StringIO.__init__(self)
        self.stdout = sys.stdout
        self.logger = logging.getLogger("root")
        sys.stdout = self

    def __del__(self) -> None:
        sys.stdout = self.stdout

    def write(self, data) -> int:
        ret = self.stdout.write(data)
        for l in data.split("\n"):
            self.logger.info(l)
        return ret

    def fileno(self) -> int:
        return self.stdout.fileno()

    def isatty(self) -> bool:
        return self.stdout.isatty()

    def flush(self) -> None:
        return self.stdout.flush()


# Borrowed from http://stackoverflow.com/questions/377017/test-if-executable-exists-in-python.
def which(program: str) -> str:
    import os

    def is_exe(fpath: str) -> bool:
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
    return type("Enum", (), enums)


def write_file(path: str, contents: str) -> None:
    with open(path, "w") as f:
        f.write(contents)


def xml_expr_to_python(node):
    res: Any
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

    raise Exception(
        "cannot convert XML output of nix-instantiate to Python: Unknown tag "
        + node.tag
    )


def parse_nixos_version(s: str) -> List[str]:
    """Split a NixOS version string into a list of components."""
    return s.split(".")


# sd -> sd
# xvd -> sd
# nvme -> sd
def device_name_to_boto_expected(string: str) -> str:
    """Transfoms device name to name, that boto expects."""
    m = re.search("(.*)\/nvme(\d+)n1p?(\d+)?", string)
    if m is not None:
        device = m.group(2)
        device_ = int(device) - 1
        device_transformed = chr(ord("f") + device_)

        partition = m.group(3) or ""

        return "{0}/sd{1}{2}".format(m.group(1), device_transformed, partition)
    else:
        return string.replace("/dev/xvd", "/dev/sd")


# sd -> sd
# xvd -> sd
# nvme -> nvme
def device_name_user_entered_to_stored(string: str) -> str:
    return string.replace("/dev/xvd", "/dev/sd")


# sd -> xvd
# xvd -> xvd
# nvme -> nvme
def device_name_stored_to_real(string: str) -> str:
    return string.replace("/dev/sd", "/dev/xvd")
