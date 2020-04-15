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

    def test_immutable_dict(self):
        d = {
            "foo": "bar",
            "list": [1, 2, 3],
            "nested": {"x": "y",},
            "nested_in_list": [{"x": "y",}],
        }

        # Assert that the shape of the immutable dict is the same as the input dict

        i = util.ImmutableMapping(d)
        self.assertEqual(d["foo"], i["foo"])

        tup = i["list"]
        self.assertTrue(isinstance(tup, tuple))
        self.assertEqual(list(tup), d["list"])

        dic = i["nested"]
        self.assertTrue(isinstance(dic, util.ImmutableMapping))
        self.assertEqual(
            dic["x"], d["nested"]["x"],
        )

        dic_l = i["nested_in_list"][0]
        self.assertTrue(isinstance(dic_l, util.ImmutableMapping))

        # Assert immutability
        def _assign():
            i["z"] = 1

        self.assertRaises(TypeError, _assign)
