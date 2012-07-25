from os.path import realpath
import fcntl
import exceptions
import errno

class StateLock:
    def __init__(self, state_file):
        self.state_file = realpath(state_file)


    def __enter__(self):
        self._state_file_lock = open(self.state_file + ".lock", "w+")
        try:
            fcntl.lockf(self._state_file_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except exceptions.IOError as e:
            if e.errno != errno.EAGAIN: raise
            # !!! Should probably combine with Deployment's logging functions somehow
            sys.stderr.write("waiting for exclusive lock on ‘{0}’...\n".format(self.state_file))
            fcntl.lockf(self._state_file_lock, fcntl.LOCK_EX)
        return self


    def __exit__(self, exception_type, exception_value, exception_traceback):
        fcntl.lockf(self._state_file_lock, fcntl.LOCK_UN)
        self._state_file_lock.close()
