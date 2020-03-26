import threading
import sys
import queue
import random
import traceback
import types
from typing import Dict, TypeVar, List, Iterable, Callable, Tuple, Optional, Type, Any


class MultipleExceptions(Exception):
    exceptions: Dict[str, BaseException]

    def __init__(self, exceptions: Dict[str, BaseException] = {}) -> None:
        self.exceptions = exceptions

    def __str__(self) -> str:
        err = "Multiple exceptions (" + str(len(self.exceptions)) + "): \n"
        for r in sorted(self.exceptions.keys()):
            err += "  * {}: {}\n".format(r, self.exceptions[r])
        return err

    def print_all_backtraces(self) -> None:
        for k, e in self.exceptions.items():
            sys.stderr.write("-" * 30 + "\n")
            for l in traceback.format_exception(type(e), e, e.__traceback__):
                sys.stderr.write(l)
            sys.stderr.flush()


# Once we're using Python 3.8, use this instead of the Any
# class Task(Protocol):
#    name: st
Task = Any
Result = TypeVar("Result")

WorkerResult = Tuple[
    Optional[Result],  # Result of the execution, None if there is an Exception
    Optional[BaseException],  # Optional Exception information
    str,  # The result of `task.name`
]


def run_tasks(
    nr_workers: int, tasks: Iterable[Task], worker_fun: Callable[[Task], Result]
) -> List[Result]:
    task_queue: queue.Queue[Task] = queue.Queue()
    result_queue: queue.Queue[WorkerResult[Result]] = queue.Queue()

    nr_tasks = 0
    for t in tasks:
        task_queue.put(t)
        nr_tasks = nr_tasks + 1

    if nr_tasks == 0:
        return []

    if nr_workers == -1:
        nr_workers = nr_tasks
    if nr_workers < 1:
        raise Exception("number of worker threads must be at least 1")

    def thread_fun() -> None:
        n = 0
        while True:
            try:
                t = task_queue.get(False)
            except queue.Empty:
                break
            n = n + 1
            work_result: WorkerResult[Result]
            try:
                work_result = (worker_fun(t), None, t.name)
            except Exception as e:
                work_result = (None, e, t.name)

            result_queue.put(work_result)
        # sys.stderr.write("thread {0} did {1} tasks\n".format(threading.current_thread(), n))

    threads = []
    for n in range(nr_workers):
        thr = threading.Thread(target=thread_fun)
        thr.daemon = True
        thr.start()
        threads.append(thr)

    results: List[Result] = []
    exceptions = {}
    found_results: int = 0
    while found_results < nr_tasks:
        try:
            # Use a timeout to allow keyboard interrupts to be
            # processed.  The actual timeout value doesn't matter.
            result: WorkerResult[Result] = result_queue.get(True, 1000)
            found_results += 1
            (res, exc, name) = result
        except queue.Empty:
            continue

        if exc:
            exceptions[name] = exc
        if res:
            results.append(res)

    for thr in threads:
        thr.join()

    if len(exceptions) == 1:
        raise list(exceptions.values())[0]

    if len(exceptions) > 1:
        raise MultipleExceptions(exceptions)

    return results
