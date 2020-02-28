import threading
import sys
import queue
import random
import traceback
import types
from typing import TypeVar, List, Callable, Tuple, Optional, Type, Any


class MultipleExceptions(Exception):
    def __init__(self, exceptions={}):
        self.exceptions = exceptions

    def __str__(self):
        err = "Multiple exceptions (" + str(len(self.exceptions)) + "): \n"
        for r in sorted(self.exceptions.keys()):
            err += "  * {}: {}\n".format(r, self.exceptions[r][1])
        return err

    def print_all_backtraces(self):
        for k, e in self.exceptions.items():
            sys.stderr.write("-" * 30 + "\n")
            traceback.print_exception(e[0], e[1], e[2])


# Once we're using Python 3.8, use this instead of the Any
# class Task(Protocol):
#    name: st
Task = Any
Result = TypeVar("Result")
ExcInfo = Tuple[Type[BaseException], BaseException, types.TracebackType]

WorkerResult = Tuple[
    Optional[Result],  # Result of the execution, None if there is an Exception
    Optional[ExcInfo],  # Optional Exception information
    str,  # The result of `task.name`
]


def run_tasks(
    nr_workers: int, tasks: List[Task], worker_fun: Callable[[Task], Result]
) -> List[Optional[Result]]:
    task_queue: queue.Queue[Task] = queue.Queue()
    result_queue: queue.Queue[WorkerResult] = queue.Queue()

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

    def thread_fun():
        n = 0
        while True:
            try:
                t = task_queue.get(False)
            except queue.Empty:
                break
            n = n + 1
            work_result: WorkerResult
            try:
                work_result = (worker_fun(t), None, t.name)
            except Exception as e:
                info = sys.exc_info()
                if info[0] is None:
                    # impossible; would only be None if we're not
                    # handling an exception ... and we are...
                    # but we have to do this anyway, to avoid
                    # propogating this bad API throughout NixOps.
                    work_result = (None, None, t.name)
                else:
                    work_result = (None, info, t.name)

            result_queue.put(work_result)
        # sys.stderr.write("thread {0} did {1} tasks\n".format(threading.current_thread(), n))

    threads = []
    for n in range(nr_workers):
        thr = threading.Thread(target=thread_fun)
        thr.daemon = True
        thr.start()
        threads.append(thr)

    results: List[Optional[Result]] = []
    exceptions = {}
    while len(results) < nr_tasks:
        try:
            # Use a timeout to allow keyboard interrupts to be
            # processed.  The actual timeout value doesn't matter.
            result: WorkerResult = result_queue.get(True, 1000)
            (res, excinfo, name) = result
        except queue.Empty:
            continue
        if excinfo:
            exceptions[name] = excinfo
        results.append(res)

    for thr in threads:
        thr.join()

    if len(exceptions) == 1:
        excinfo = exceptions[next(iter(exceptions.keys()))]
        raise excinfo[0](excinfo[1]).with_traceback(excinfo[2])

    if len(exceptions) > 1:
        raise MultipleExceptions(exceptions)

    return results
