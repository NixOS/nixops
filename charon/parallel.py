import threading
import sys
import Queue
import random

def run_tasks(nr_workers, tasks, worker_fun):
    task_queue = Queue.Queue()
    result_queue = Queue.Queue()

    nr_tasks = 0
    for t in tasks: task_queue.put(t); nr_tasks = nr_tasks + 1

    def thread_fun():
        n = 0
        while True:
            try:
                t = task_queue.get(False)
            except Queue.Empty:
                break
            n = n + 1
            try:
                result_queue.put((worker_fun(t), None, None))
            except Exception as e:
                result_queue.put((None, e, sys.exc_info()[2]))
        #sys.stderr.write("thread {0} did {1} tasks\n".format(threading.current_thread(), n))
        
    threads = []
    for n in range(nr_workers):
        thr = threading.Thread(target=thread_fun)
        thr.daemon = True
        thr.start()
        threads.append(thr)

    results = []
    while len(results) < nr_tasks:
        try:
            # Use a timeout to allow keyboard interrupts to be
            # processed.  The actual timeout value doesn't matter.
            (res, exc, tb) = result_queue.get(True, 1000)
        except Queue.Empty:
            continue
        if exc:
            raise exc, None, tb
        results.append(res)
        
    for thr in threads:
        thr.join()

    return results
