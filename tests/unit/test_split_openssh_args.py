import unittest

from nixops.transports.ssh import SSH


class SplitSSHArgs(unittest.TestCase):
    def assert_split(self, orig, expected_flags, expected_command):
        flags, command = SSH.split_openssh_args(orig)
        self.assertEqual(flags, expected_flags)
        self.assertEqual(command, expected_command)

    def test_empty(self):
        self.assert_split([], [], [])

    def test_invalid(self):
        self.assert_split(["-o"], ["-o"], [])
        self.assert_split(["-xo"], ["-x", "-o"], [])
        self.assert_split(["--", "-ox"], [], ["-ox"])
        self.assert_split(["-"], ["-"], [])
        self.assert_split(["--help"], ["--help"], [])

    def test_simple(self):
        self.assert_split(["-x12", "command"], ["-x", "-1", "-2"], ["command"])
        self.assert_split(["-oOpt", "command"], ["-oOpt"], ["command"])
        self.assert_split(["-oOpt", "--", "command"], ["-oOpt"], ["command"])
        self.assert_split(["ls", "-l", "--", "x"], [], ["ls", "-l", "--", "x"])

    def test_mixed(self):
        self.assert_split(["-xoFoo", "xxx"], ["-x", "-oFoo"], ["xxx"])
        self.assert_split(["-1_oFoo", "xxx"], ["-1", "-_", "-oFoo"], ["xxx"])
