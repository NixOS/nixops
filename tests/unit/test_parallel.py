import functools
import unittest
from typing import Callable, Any

from nixops.parallel import run_tasks, MultipleExceptions

__all__ = ["ParallelTest"]


class ExampleTask:
    name: str
    todo: Callable[[], Any]

    def __init__(self, name, todo):
        self.name = name
        self.todo = todo


class ComplexException(Exception):
    def __init__(self, arg1: str, arg2: str) -> None:
        pass


def err(msg: str):
    raise Exception(msg)


def complex_err(msg1: str, msg2: str):
    raise ComplexException(msg1, msg2)


class ParallelTest(unittest.TestCase):
    def test_okay(self):
        self.assertEqual(
            run_tasks(
                1,
                [ExampleTask("foo", lambda: "ok"), ExampleTask("bar", lambda: "ok"),],
                lambda task: task.todo(),
            ),
            ["ok", "ok"],
        )

    def test_one_exception(self):
        self.assertRaises(
            Exception,
            run_tasks,
            1,
            [
                ExampleTask("foo", lambda: "ok"),
                ExampleTask("bar", lambda: err("oh no")),
            ],
            lambda task: task.todo(),
        )

    def test_two_exceptions(self):
        self.assertRaises(
            MultipleExceptions,
            run_tasks,
            1,
            [
                ExampleTask("foo", lambda: err("uh oh")),
                ExampleTask("bar", lambda: err("oh no")),
            ],
            lambda task: task.todo(),
        )

    def test_complicated_exception(self):
        self.assertRaises(
            ComplexException,
            run_tasks,
            1,
            [ExampleTask("foo", lambda: complex_err("uh", "oh")),],
            lambda task: task.todo(),
        )

    def test_complicated_two_exceptions(self):
        self.assertRaises(
            MultipleExceptions,
            run_tasks,
            1,
            [
                ExampleTask("foo", lambda: complex_err("uh", "oh")),
                ExampleTask("baz", lambda: err("oh no")),
            ],
            lambda task: task.todo(),
        )
