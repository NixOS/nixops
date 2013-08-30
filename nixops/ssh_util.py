# -*- coding: utf-8 -*-
import os
import sys
import tty
import fcntl
import errno
import struct
import select
import signal
import termios

from contextlib import contextmanager

import paramiko

import nixops.util

__all__ = ['SSHConnectionFailed', 'SSHCommandFailed', 'SSH']


class SSHConnectionFailed(Exception):
    pass


class SSHCommandFailed(nixops.util.CommandFailed):
    pass


class SSHConnection(object):
    def __init__(self, ssh, host):
        self.ssh = ssh
        self.host = host

    def invoke_shell(self, command=None):
        """
        Invoke a 'command' on the target machine while allocating a PTY.

        This is only meant to be used for interactive shells or programs and
        doesn't directly allow for logging, such as run_command().
        """
        transport = self.ssh.get_transport()
        channel = transport.open_session()

        def _get_term_size():
            winsz = fcntl.ioctl(sys.stdin.fileno(), termios.TIOCGWINSZ, '....')
            return struct.unpack('hh', winsz)

        def _winch_handler(signum, frame):
            height, width = _get_term_size()
            channel.resize_pty(width=width, height=height)

        height, width = _get_term_size()
        current_term = os.getenv('TERM', 'vt100')
        channel.get_pty(current_term, width=width, height=height)
        if command is None:
            channel.invoke_shell()
        else:
            channel.exec_command(command)

        oldtty = termios.tcgetattr(sys.stdin)
        oldflags = fcntl.fcntl(sys.stdin.fileno(), fcntl.F_GETFL)
        oldsig = signal.signal(signal.SIGWINCH, _winch_handler)
        signal.siginterrupt(signal.SIGWINCH, False)
        try:
            tty.setraw(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
            fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFL,
                        oldflags | os.O_NDELAY)
            channel.setblocking(0)

            while True:
                try:
                    ready = select.select([channel, sys.stdin], [], [])[0]
                except select.error as e:
                    if e.args[0] == errno.EINTR:
                        continue
                    else:
                        raise
                if channel in ready:
                    data = channel.recv(1)
                    if len(data) == 0:
                        break
                    sys.stdout.write(data)
                    sys.stdout.flush()
                if sys.stdin in ready:
                    data = sys.stdin.read()
                    if len(data) == 0:
                        break
                    channel.send(data)
        finally:
            signal.signal(signal.SIGWINCH, oldsig)
            fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFL, oldflags)
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, oldtty)

    def upload(self, source, destination):
        """
        Upload the local file 'source' to the current host at 'destination'.
        """
        sftp = paramiko.SFTPClient.from_transport(self.ssh.get_transport())
        sftp.put(source, destination)

    def download(self, source, target):
        """
        Download the file 'source' from the current host to local file 'target'.
        """
        sftp = paramiko.SFTPClient.from_transport(self.ssh.get_transport())
        sftp.get(source, target)

    @contextmanager
    def open(self, *args, **kwargs):
        """
        Open a file instance on the remote side. This is the same as Python's
        open() function but working on the remote file and using a context
        manager. So you only can use this method using the with keyword.
        """
        sftp = paramiko.SFTPClient.from_transport(self.ssh.get_transport())
        fp = sftp.open(*args, **kwargs)
        yield fp
        fp.close()

    def run_command(self, command, timeout=None, log_cb=None, bufsize=4096,
                    stdin_string=None, stdin=None, capture_stdout=False,
                    check=True):
        """
        Execute a 'command' on the current target host using SSH. The command
        can be either a string or an iterable of strings, whereby if it's the
        latter, it will be joined with spaces and properly shell-escaped.

        TODO: document keyword arguments!

        'log_cb' is either None for no logging or a function which is called
        whenever there is data on either stdout (if 'capture_stdout' is False)
        or stderr of the command.
        """
        transport = self.ssh.get_transport()
        channel = transport.open_session()
        channel.exec_command(command)

        if not capture_stdout:
            channel.set_combine_stderr(True)

        stdin_done = stdin_string is None and stdin is None
        stdout = ""
        buf = ""
        while not channel.eof_received and not channel.closed:
            if not stdin_done and channel.send_ready():
                if stdin_string is not None:
                    sent = channel.send(stdin_string[:bufsize])
                    stdin_string = stdin_string[sent:]
                    if sent == 0:
                        stdin_done = True
                elif stdin is not None:
                    if len(buf) == 0:
                        buf = stdin.read(bufsize)
                        if len(buf) == 0:
                            stdin_done = True
                    sent = channel.send(buf)
                    buf = buf[sent:]

                if stdin_done:
                    channel.shutdown_write()

            if capture_stdout:
                while channel.recv_stderr_ready():
                    data = channel.recv_stderr(bufsize)
                    if log_cb is not None:
                        log_cb(data)

            while channel.recv_ready():
                data = channel.recv(bufsize)
                if capture_stdout:
                    stdout += data
                elif log_cb is not None:
                    log_cb(data)

        exitcode = channel.recv_exit_status()
        if check and exitcode != 0:
            msg = "command ‘{0}’ failed on host ‘{1}’"
            err = msg.format(command, self.host)
            raise SSHCommandFailed(err, exitcode)

        if capture_stdout:
            return stdout
        else:
            return exitcode


class SSH(object):
    def __init__(self):
        """
        Initialize a SSH object with the specified Logger instance, which will
        be used to write SSH output to.
        """
        pass

    def connect(self, host, port=22, privkey=None, username='root',
                passwd=None, timeout=None):
        """
        Connect to 'host' and 'port' using either 'privkey' which is a string
        (XXX: currently it's a file) containing the private key to be used for
        authentication or 'passwd' which is the password of the account
        specified by 'username' ("root" by default).

        Returns a new instance of SSHConnection.
        """
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())
        ssh.connect(host, username=username, key_filename=privkey,
                    password=passwd, port=port, timeout=timeout)
        return SSHConnection(ssh, host)
