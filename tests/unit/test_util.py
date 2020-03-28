from nixops.logger import Logger
from io import StringIO
import unittest

from nixops import util


class TestUtilTest(unittest.TestCase):
    def setUp(self):
        self.logfile = StringIO()
        self.root_logger = Logger(self.logfile)
        self.logger = self.root_logger.get_logger_for("dummymachine")

    def test_assert_logged_exec(self):
        msg = "hello"

        ret = util.logged_exec(
            command=["cat"], logger=self.logger, stdin_string=msg, capture_stdout=True,
        )

        self.assertEqual(ret, msg)

    def test_assert_logged_exec_stdin_none(self):
        msg = "hello"

        ret = util.logged_exec(
            command=["echo", msg], logger=self.logger, capture_stdout=True,
        )

        self.assertEqual(ret.strip(), msg)
