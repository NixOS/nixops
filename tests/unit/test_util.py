from typing import Sequence
import json
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
            command=["cat"],
            logger=self.logger,
            stdin_string=msg,
            capture_stdout=True,
        )

        self.assertEqual(ret, msg)

    def test_assert_logged_exec_stdin_none(self):
        msg = "hello"

        ret = util.logged_exec(
            command=["echo", msg],
            logger=self.logger,
            capture_stdout=True,
        )
        if not isinstance(ret, str):
            raise ValueError("Wrong return type!")

        self.assertEqual(ret.strip(), msg)

    def test_immutable_dict(self):
        d = {
            "foo": "bar",
            "list": [1, 2, 3],
            "nested": {"x": "y"},
            "nested_in_list": [{"x": "y"}],
        }

        # Assert that the shape of the immutable dict is the same as the input dict

        i = util.ImmutableMapping(d)
        self.assertEqual(d["foo"], i["foo"])

        tup = i["list"]
        self.assertTrue(isinstance(tup, tuple))
        self.assertEqual(list(tup), d["list"])

        # Ensure our encoder round-trips okay
        self.assertEqual(json.dumps(i, cls=util.NixopsEncoder), json.dumps(d))

        dic = i["nested"]
        self.assertTrue(isinstance(dic, util.ImmutableMapping))
        self.assertEqual(
            dic["x"],
            d["nested"]["x"],
        )

        dic_l = i["nested_in_list"][0]
        self.assertTrue(isinstance(dic_l, util.ImmutableMapping))

        # Assert immutability
        def _assign():
            i["z"] = 1

        self.assertRaises(TypeError, _assign)

    def test_immutable_object(self):
        class SubResource(util.ImmutableValidatedObject):
            x: int

        class HasSubResource(util.ImmutableValidatedObject):
            sub: SubResource

        r = HasSubResource(sub={"x": 1})
        self.assertTrue(isinstance(r.sub.x, int))
        self.assertEqual(r.sub.x, 1)

        self.assertRaises(TypeError, lambda: SubResource(x="a string"))

        def _assign():
            r = SubResource(x=1)
            r.x = 2

        self.assertRaises(AttributeError, _assign)

        # Fuzz not passed, should raise TypeError
        class MustRaise(util.ImmutableValidatedObject):
            fuzz: str

        self.assertRaises(TypeError, lambda: MustRaise())

        class WithDefaults(util.ImmutableValidatedObject):
            x: int = 1

        self.assertEqual(WithDefaults().x, 1)

        # Extensible
        class A(util.ImmutableValidatedObject):
            x: int

        class B(A):
            y: int

        a = A(x=1)
        b = B(a, y=1)
        self.assertEqual(a.x, b.x)
        self.assertEqual(b.x, 1)

        # Test Sequence[ImmutableValidatedObject]
        class WithSequence(util.ImmutableValidatedObject):
            subs: Sequence[SubResource]

        WithSequence(subs=[SubResource(x=1), SubResource(x=2)])
