import unittest

from StringIO import StringIO

from nixops.logger import Logger

class RootLoggerTest(unittest.TestCase):
    def setUp(self):
        self.logfile = StringIO()
        self.root_logger = Logger(self.logfile)

    def assert_log(self, value):
        self.assertEquals(self.logfile.getvalue(), value)

    def test_simple(self):
        self.root_logger.log("line1")
        self.assert_log("line1\n")
        self.root_logger.log("line2")
        self.assert_log("line1\nline2\n")

    def test_prefix(self):
        self.root_logger.log_start("xxx: ", "foo")
        self.root_logger.log_end("xxx: ", "bar")
        self.assert_log("xxx: foobar\n")

    def test_prefix_mixed(self):
        self.root_logger.log_start("xxx: ", "begin1")
        self.root_logger.log_start("yyy: ", "begin2")
        self.root_logger.log_end("xxx: ", "end1")
        self.root_logger.log_end("yyy: ", "end2")
        self.assert_log("xxx: begin1\nyyy: begin2\nxxx: end1\nyyy: end2\n")

class MachineLoggerTest(RootLoggerTest):
    def setUp(self):
        RootLoggerTest.setUp(self)
        self.m1_logger = self.root_logger.get_logger_for("machine1", 1)
        self.m2_logger = self.root_logger.get_logger_for("machine2", 2)

    def test_simple(self):
        self.m2_logger.success("success!")
        self.m1_logger.warn("warning!")
        self.assert_log("machine2> success!\nmachine1> warning: warning!\n")

    def test_continue(self):
        self.m1_logger.log_start("Begin...")
        for dummy in range(10):
            self.m1_logger.log_continue(".")
        self.m1_logger.log_end("end.")
        self.assert_log("machine1> Begin.............end.\n")

    def test_continue_mixed(self):
        self.m1_logger.log_start("Begin 1...")
        self.m2_logger.log_start("Begin 2...")

        for dummy in range(10):
            self.m1_logger.log_continue(".")
            self.m2_logger.log_continue(".")

        self.m1_logger.log_end("end 1.")
        self.m2_logger.log_end("end 2.")
        self.assert_log("machine1> Begin 1...\nmachine2> Begin 2...\n"
                        "machine1> .\nmachine2> .\nmachine1> .\nmachine2> .\n"
                        "machine1> .\nmachine2> .\nmachine1> .\nmachine2> .\n"
                        "machine1> .\nmachine2> .\nmachine1> .\nmachine2> .\n"
                        "machine1> .\nmachine2> .\nmachine1> .\nmachine2> .\n"
                        "machine1> .\nmachine2> .\nmachine1> .\nmachine2> .\n"
                        "machine1> end 1.\nmachine2> end 2.\n")
