import os
import unittest
import socket
import threading
import itertools
import difflib

from StringIO import StringIO

import paramiko

from nixops.ssh_util import SSH


class TestSSHServer(paramiko.ServerInterface):
    def get_allowed_auths(self):
        return 'publickey,password'

    def check_auth_password(self, user, passwd):
        return paramiko.AUTH_SUCCESSFUL

    def check_auth_publickey(self, user, key):
        return paramiko.AUTH_SUCCESSFUL

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED

    def check_channel_exec_request(self, channel, command):
        self.command = command
        return True


class StringLogger(object):
    """
    A dummy Logger implementation that just gathers all data into a string.
    """
    def __init__(self):
        self.data = ""

    def log_start(self, msg):
        self.data += msg


class SSHTest(unittest.TestCase):
    HOST_KEY = paramiko.RSAKey.generate(1024)
    BUFSIZE = 1024

    def setUp(self):
        self.sock = socket.socket()
        self.sock.bind(('localhost', 0))
        self.sock.listen(1)
        self.addr, self.port = self.sock.getsockname()
        self.trigger = threading.Event()

        threading.Thread(target=self.run_server).start()

    def tearDown(self):
        # Just ping the socket to ensure it won't block if something goes wrong
        # before the first connect.
        socket.create_connection((self.addr, self.port)).close()

        for attrname in ('transport', 'server', 'sock'):
            attr = getattr(self, attrname, None)
            if attr is not None:
                attr.close()

    def run_server(self):
        self.server, addr = self.sock.accept()
        self.transport = paramiko.Transport(self.server)
        self.transport.add_server_key(self.HOST_KEY)
        self.transport.start_server(self.trigger, TestSSHServer())

        channel = self.transport.accept(10)
        command = self.transport.server_object.command
        for i in itertools.count():
            data = channel.recv(self.BUFSIZE)
            if len(data) == 0:
                break
            if command == 'oddeven':
                if i % 2 == 0:
                    channel.send(data)
                else:
                    channel.send_stderr(data)
            elif command == 'stdout':
                channel.send(data)
            elif command == 'stderr':
                channel.send_stderr(data)
        channel.send_exit_status(0)
        channel.close()

    def connect_client(self):
        ssh = SSH()
        client = ssh.connect(self.addr, port=self.port, passwd='')
        self.trigger.wait(1.0)
        self.assertTrue(self.trigger.isSet())
        self.assertTrue(self.transport.is_authenticated())
        return client

    def pprint_text(self, text):
        if len(text) > 20:
            return "{0}... ({1} bytes)".format(text[:20], len(text))
        else:
            return text

    def assert_textdiff(self, expect, result):
        if expect == result:
            return

        delta = difflib.SequenceMatcher(a=expect, b=result)
        diffs = []

        for tag, i1, i2, j1, j2 in delta.get_opcodes():
            if tag == 'delete':
                msg = '{0} missing at position {1}'
                diffs.append(msg.format(self.pprint_text(expect[i1:i2]), j1))
            elif tag == 'replace':
                msg = 'expected {0} at position {1}, but got {2} instead'
                diffs.append(msg.format(self.pprint_text(expect[i1:i2]), j1,
                                        self.pprint_text(result[j1:j2])))
            elif tag == 'insert':
                msg = 'excess {0} at position {1}'
                diffs.append(msg.format(self.pprint_text(result[j1:j2]), i1))

        self.fail(', '.join(diffs))

    def test_stream_passthrough(self):
        client = self.connect_client()
        payload = ('A' * self.BUFSIZE + 'B' * self.BUFSIZE) * 100
        stdin = StringIO(payload)
        output = client.run_command("oddeven", stdin=stdin,
                                    capture_stdout=True)

        self.assert_textdiff('A' * self.BUFSIZE * 100, output)

    def test_string_passthrough(self):
        client = self.connect_client()
        payload = ('A' * self.BUFSIZE + 'B' * self.BUFSIZE) * 100
        output = client.run_command("oddeven", stdin_string=payload,
                                    capture_stdout=True)

        self.assert_textdiff('A' * self.BUFSIZE * 100, output)

    def test_stdout_only(self):
        client = self.connect_client()
        payload = 'O' * self.BUFSIZE * 100
        output = client.run_command("stdout", stdin_string=payload,
                                    capture_stdout=True)

        self.assert_textdiff(payload, output)

    def test_stderr_only(self):
        client = self.connect_client()
        payload = 'E' * self.BUFSIZE * 100
        stderr = StringLogger()
        output = client.run_command("stderr", stdin_string=payload,
                                    capture_stdout=True, logger=stderr)

        self.assert_textdiff(payload, stderr.data)
