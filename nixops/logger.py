# -*- coding: utf-8 -*-
import threading

from nixops.util import ansi_warn, ansi_success

__all__ = ['Logger']


class Logger(object):
    def __init__(self, log_file):
        self._last_log_prefix = None  # XXX!
        self._log_lock = threading.Lock()
        self._log_file = log_file
        self.machine_loggers = []

    @property
    def log_file(self):
        # XXX: Remove me soon!
        return self._log_file

    def isatty(self):
        return self._log_file.isatty()

    def log(self, msg):
        with self._log_lock:
            if self._last_log_prefix is not None:
                self._log_file.write("\n")
                self._last_log_prefix = None
            self._log_file.write(msg + "\n")

    def log_start(self, prefix, msg):
        with self._log_lock:
            if self._last_log_prefix != prefix:
                if self._last_log_prefix is not None:
                    self._log_file.write("\n")
                self._log_file.write(prefix)
            self._log_file.write(msg)
            self._last_log_prefix = prefix

    def log_end(self, prefix, msg):
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

    def get_logger_for(self, machine_name, index):
        """
        Returns a logger instance for a specific machine name.
        """
        machine_logger = MachineLogger(self, machine_name, index)
        self.machine_loggers.append(machine_logger)
        self.update_log_prefixes()
        return machine_logger

    def update_log_prefixes(self):
        max_len = max([len(ml.machine_name)
                       for ml in self.machine_loggers] or [0])
        for ml in self.machine_loggers:
            ml.update_log_prefix(max_len)

    def warn(self, msg):
        self.log(ansi_warn("warning: " + msg, outfile=self._log_file))

    def confirm_once(self, question, autoresponse=None):
        with self._log_lock:
            if self._last_log_prefix is not None:
                self._log_file.write("\n")
                self._last_log_prefix = None
            self.warn("warning: {0} (y/N) ".format(question))
            if auto_response is not None:
                self._log_file.write("{0}\n".format(self.auto_response))
                return auto_response == "y"
            response = sys.stdin.readline()
            if response == "":
                return False
            response = response.rstrip().lower()
            if response == "y":
                return True
            if response == "n" or response == "":
                return False

    def confirm(self, question, autoresponse=None):
        while True:
            self.confirm_once(question, autoresponse)


class MachineLogger(object):
    def __init__(self, main_logger, machine_name, index):
        self.main_logger = main_logger
        self.machine_name = machine_name
        self.index = index
        self.update_log_prefix(0)

    def update_log_prefix(self, length):
        self._log_prefix = "{0}{1}> ".format(
            self.machine_name,
            '.' * (length - len(self.machine_name))
        )
        if self.main_logger.isatty() and self.index is not None:
            self._log_prefix = "\033[1;{0}m{1}\033[0m".format(
                31 + self.index % 7, self._log_prefix
            )

    def log(self, msg):
        self.main_logger.log(self._log_prefix + msg)

    def log_start(self, msg):
        self.main_logger.log_start(self._log_prefix, msg)

    def log_continue(self, msg):
        self.main_logger.log_start(self._log_prefix, msg)

    def log_end(self, msg):
        self.main_logger.log_end(self._log_prefix, msg)

    def warn(self, msg):
        self.log(ansi_warn("warning: " + msg,
                           outfile=self.main_logger._log_file))

    def success(self, msg):
        self.log(ansi_success(msg, outfile=self.main_logger._log_file))
