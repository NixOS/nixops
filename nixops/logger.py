# -*- coding: utf-8 -*-
import sys
import threading

from nixops.util import ansi_warn, ansi_error, ansi_success

__all__ = ["Logger"]


class Logger(object):
    def __init__(self, log_file):
        self._last_log_prefix = None  # XXX!
        self._log_lock = threading.Lock()
        self._log_file = log_file
        self._auto_response = None
        self.machine_loggers = []

    @property
    def log_file(self):
        # XXX: Remove me soon!
        return self._log_file

    def isatty(self):
        return self._log_file.isatty()

    def log(self, msg):
        msg = msg if isinstance(msg, str) else msg.decode("utf-8")
        with self._log_lock:
            if self._last_log_prefix is not None:
                self._log_file.write("\n")
                self._last_log_prefix = None
            self._log_file.write(msg + "\n")
            self._log_file.flush()

    def log_start(self, prefix, msg):
        msg = msg if isinstance(msg, str) else msg.decode("utf-8")
        with self._log_lock:
            if self._last_log_prefix != prefix:
                if self._last_log_prefix is not None:
                    self._log_file.write("\n")
                self._log_file.write(prefix)
            self._log_file.write(msg)
            self._last_log_prefix = prefix
            self._log_file.flush()

    def log_end(self, prefix, msg):
        msg = msg if isinstance(msg, str) else msg.decode("utf-8")
        with self._log_lock:
            last = self._last_log_prefix
            self._last_log_prefix = None
            if last != prefix:
                if last is not None:
                    self._log_file.write("\n")
                if msg == "":
                    return
                self._log_file.write(prefix)
            self._log_file.write(msg + "\n")
            self._log_file.flush()

    def get_logger_for(self, machine_name):
        """
        Returns a logger instance for a specific machine name.
        """
        machine_logger = MachineLogger(self, machine_name)
        self.machine_loggers.append(machine_logger)
        self.update_log_prefixes()
        return machine_logger

    def set_autoresponse(self, response):
        """
        Automatically respond to all confirmations with the response given by
        'response'.
        """
        self._auto_response = response

    def update_log_prefixes(self):
        max_len = max([len(ml.machine_name) for ml in self.machine_loggers] or [0])
        for ml in self.machine_loggers:
            ml.update_log_prefix(max_len)

    def warn(self, msg):
        msg = msg if isinstance(msg, str) else msg.decode("utf-8")
        self.log(ansi_warn("warning: " + msg, outfile=self._log_file))

    def error(self, msg):
        msg = msg if isinstance(msg, str) else msg.decode("utf-8")
        self.log(ansi_error("error: " + msg, outfile=self._log_file))

    def confirm_once(self, question):
        with self._log_lock:
            if self._last_log_prefix is not None:
                self._log_file.write("\n")
                self._last_log_prefix = None
            # XXX: This should be DRY!
            self._log_file.write(
                ansi_warn(
                    "warning: {0} (y/N) ".format(question), outfile=self._log_file
                )
            )
            self._log_file.flush()
            if self._auto_response is not None:
                self._log_file.write("{0}\n".format(self._auto_response))
                self._log_file.flush()
                return self._auto_response == "y"
            response = sys.stdin.readline()
            if response == "":
                return False
            response = response.rstrip().lower()
            if response == "y":
                return True
            if response == "n" or response == "":
                return False
        return None

    def confirm(self, question):
        ret = None
        while ret is None:
            ret = self.confirm_once(question)
        return ret


class MachineLogger(object):
    def __init__(self, main_logger, machine_name):
        self.main_logger = main_logger
        self.machine_name = machine_name
        self.index = None
        self.update_log_prefix(0)

    def register_index(self, index):
        # FIXME Find a good way to do coloring based on machine name only.
        self.index = index

    def update_log_prefix(self, length):
        self._log_prefix = "{0}{1}> ".format(
            self.machine_name, "." * (length - len(self.machine_name))
        )
        if self.main_logger.isatty() and self.index is not None:
            self._log_prefix = "\033[1;{0}m{1}\033[0m".format(
                31 + self.index % 7, self._log_prefix
            )

    def log(self, msg):
        self.main_logger.log(
            self._log_prefix + (msg if isinstance(msg, str) else msg.decode("utf-8"))
        )

    def log_start(self, msg):
        self.main_logger.log_start(self._log_prefix, msg)

    def log_continue(self, msg):
        self.main_logger.log_start(self._log_prefix, msg)

    def log_end(self, msg):
        self.main_logger.log_end(self._log_prefix, msg)

    def warn(self, msg):
        self.log(ansi_warn("warning: " + msg, outfile=self.main_logger._log_file))

    def error(self, msg):
        self.log(ansi_error("error: " + msg, outfile=self.main_logger._log_file))

    def success(self, msg):
        self.log(ansi_success(msg, outfile=self.main_logger._log_file))
