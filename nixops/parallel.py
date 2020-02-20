import threading
import sys
import queue
import random
import traceback


class MultipleExceptions(Exception):
    def __init__(self, exceptions={}):
        self.exceptions = exceptions

    def __str__(self):
        err = "Multiple exceptions (" + str(len(list(self.exceptions.keys()))) + "): \n"
        for r in sorted(self.exceptions.keys()):
            err += "  * {}: {}\n".format(r, self.exceptions[r][1])
        return err

    def print_all_backtraces(self):
        for k, e in list(self.exceptions.items()):
            sys.stderr.write("-" * 30 + "\n")
            traceback.print_exception(e[0], e[1], e[2])


def run_tasks(nr_workers, tasks, worker_fun):
    task_queue = queue.Queue()
    result_queue = queue.Queue()

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
            try:
                result_queue.put((worker_fun(t), None, t.name))
            except Exception as e:
                result_queue.put((None, sys.exc_info(), t.name))
        # sys.stderr.write("thread {0} did {1} tasks\n".format(threading.current_thread(), n))

    threads = []
    for n in range(nr_workers):
        thr = threading.Thread(target=thread_fun)
        thr.daemon = True
        thr.start()
        threads.append(thr)

    results = []
    exceptions = {}
    while len(results) < nr_tasks:
        try:
            # Use a timeout to allow keyboard interrupts to be
            # processed.  The actual timeout value doesn't matter.
            (res, excinfo, name) = result_queue.get(True, 1000)
        except queue.Empty:
            continue
        if excinfo:
            exceptions[name] = excinfo
        results.append(res)

    for thr in threads:
        thr.join()

    if len(list(exceptions.keys())) == 1:
        excinfo = exceptions[list(exceptions.keys())[0]]
        raise excinfo[0](excinfo[1]).with_traceback(excinfo[2])

    if len(list(exceptions.keys())) > 1:
        raise MultipleExceptions(exceptions)

    return results
