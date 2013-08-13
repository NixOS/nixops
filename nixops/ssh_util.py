# -*- coding: utf-8 -*-
import os
import sys
import tty
import shlex
import fcntl
import struct
import select
import termios

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

    def invoke_shell(self):
        transport = self.ssh.get_transport()
        channel = transport.open_session()

        current_term = os.getenv('TERM', 'vt100')
        winsz = fcntl.ioctl(0, termios.TIOCGWINSZ, '....')
        height, width = struct.unpack('hh', winsz)

        channel.get_pty(current_term, width=width, height=height)
        channel.invoke_shell()

        # This is from paramiko/demos/interactive.py
        oldtty = termios.tcgetattr(sys.stdin)
        try:
            tty.setraw(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
            channel.setblocking(0)

            while True:
                r, w, e = select.select([channel, sys.stdin], [], [])
                if channel in r:
                    try:
                        x = channel.recv(1024)
                        if len(x) == 0:
                            break
                        sys.stdout.write(x)
                        sys.stdout.flush()
                    except socket.timeout:
                        pass
                if sys.stdin in r:
                    x = sys.stdin.read(1)
                    if len(x) == 0:
                        break
                    channel.send(x)
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, oldtty)

    def run_command(self, command, timeout=None, logger=None, bufsize=4096,
                    stdin_string=None, stdin=None, capture_stdout=False,
                    check=True):
        """
        Execute a 'command' on the current target host using SSH. The command
        can be either a string or an iterable of strings, whereby if it's the
        latter, it will be joined with spaces and properly shell-escaped.

        TODO: document keyword arguments!

        'logger' is either None for no logging or a valid Logger instance,
        which then is used to log stdout (if 'capture_stdout' is False) and
        stderr of the command.
        """
        transport = self.ssh.get_transport()
        channel = transport.open_session()
        channel.exec_command(command)

        if not capture_stdout:
            channel.set_combine_stderr(True)

        stdin_done = stdin_string is None and stdin is None
        stdout = ""
        while not channel.eof_received:
            if not stdin_done and channel.send_ready():
                if stdin_string is not None:
                    sent = channel.send(stdin_string[:bufsize])
                    stdin_string = stdin_string[sent:]
                elif stdin is not None:
                    buf = stdin.read(bufsize)
                    sent = channel.send(buf)

                if sent != bufsize:
                    stdin_done = True
                    channel.shutdown_write()

                if not channel.recv_ready():
                    continue

            if capture_stdout and channel.recv_stderr_ready():
                data = channel.recv_stderr(bufsize)
                if logger is not None:
                    logger.log_start(data)

            data = channel.recv(bufsize)
            if capture_stdout:
                stdout += data
            elif logger is not None:
                logger.log_start(data)

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
