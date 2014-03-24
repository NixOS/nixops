# -*- coding: utf-8 -*-
import os
import shlex
import subprocess
import weakref

from tempfile import mkdtemp

import nixops.util

__all__ = ['SSHConnectionFailed', 'SSHCommandFailed', 'SSH']


class SSHConnectionFailed(Exception):
    pass


class SSHCommandFailed(nixops.util.CommandFailed):
    pass


class SSHMaster(object):
    def __init__(self, target, logger, ssh_flags, passwd):
        self._tempdir = mkdtemp(prefix="nixops-tmp")
        self._askpass_helper = None
        self._control_socket = self._tempdir + "/ssh-master-socket"
        self._ssh_target = target
        pass_prompts = 0
        kwargs = {}
        additional_opts = []
        if passwd is not None:
            self._askpass_helper = self._make_askpass_helper()
            newenv = dict(os.environ)
            newenv.update({
                'DISPLAY': ':666',
                'SSH_ASKPASS': self._askpass_helper,
                'NIXOPS_SSH_PASSWORD': passwd,
            })
            kwargs['env'] = newenv
            kwargs['stdin'] = nixops.util.devnull
            kwargs['preexec_fn'] = os.setsid
            pass_prompts = 1
            additional_opts = ['-oUserKnownHostsFile=/dev/null',
                               '-oStrictHostKeyChecking=no']
        cmd = ["ssh", "-x", self._ssh_target, "-S",
               self._control_socket, "-M", "-N", "-f",
               '-oNumberOfPasswordPrompts={0}'.format(pass_prompts),
               '-oServerAliveInterval=60'] + additional_opts
        res = subprocess.call(cmd + ssh_flags, **kwargs)
        if res != 0:
            raise SSHConnectionFailed(
                "unable to start SSH master connection to "
                "‘{0}’".format(logger.machine_name)
            )
        self.opts = ["-oControlPath={0}".format(self._control_socket)]

    def _make_askpass_helper(self):
        """
        Create a SSH_ASKPASS helper script, which just outputs the contents of
        the environment variable NIXOPS_SSH_PASSWORD.
        """
        path = os.path.join(self._tempdir, 'nixops-askpass-helper')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0777)
        os.write(fd, "#!{0}\necho -n \"$NIXOPS_SSH_PASSWORD\"".format(
            nixops.util.which("sh")
        ))
        os.close(fd)
        return path

    def shutdown(self):
        """
        Shutdown master process and clean up temporary files.
        """
        subprocess.call(["ssh", self._ssh_target, "-S",
                         self._control_socket, "-O", "exit"],
                        stderr=nixops.util.devnull)
        for to_unlink in (self._askpass_helper, self._control_socket):
            if to_unlink is None:
                continue
            try:
                os.unlink(to_unlink)
            except OSError:
                pass
        try:
            os.rmdir(self._tempdir)
        except OSError:
            pass

    def __del__(self):
        self.shutdown()


class SSH(object):
    def __init__(self, logger):
        """
        Initialize a SSH object with the specified Logger instance, which will
        be used to write SSH output to.
        """
        self._flag_fun = lambda: []
        self._host_fun = None
        self._passwd_fun = lambda: None
        self._logger = logger
        self._ssh_master = None

    def register_host_fun(self, host_fun):
        """
        Register a function which returns the hostname or IP to connect to. The
        function has to require no arguments.
        """
        self._host_fun = host_fun

    def _get_target(self):
        if self._host_fun is None:
            raise AssertionError("don't know which SSH host to connect to")
        return "root@{0}".format(self._host_fun())

    def register_flag_fun(self, flag_fun):
        """
        Register a function that is used for obtaining additional SSH flags.
        The function has to require no arguments and should return a list of
        strings, each being a SSH flag/argument.
        """
        self._flag_fun = flag_fun

    def _get_flags(self):
        return self._flag_fun()

    def register_passwd_fun(self, passwd_fun):
        """
        Register a function that returns either a string or None and requires
        no arguments. If the return value is a string, the returned string is
        used for keyboard-interactive authentication, if it is None, no attempt
        is made to inject a password.
        """
        self._passwd_fun = passwd_fun

    def _get_passwd(self):
        return self._passwd_fun()

    def reset(self):
        """
        Reset SSH master connection.
        """
        if self._ssh_master is not None:
            self._ssh_master.shutdown()
            self._ssh_master = None

    def get_master(self, flags=[], tries=5):
        """
        Start (if necessary) an SSH master connection to speed up subsequent
        SSH sessions. Returns the SSHMaster instance on success.
        """
        flags = flags + self._get_flags()
        if self._ssh_master is not None:
            return weakref.proxy(self._ssh_master)

        while True:
            try:
                self._ssh_master = SSHMaster(self._get_target(), self._logger,
                                             flags, self._get_passwd())
                break
            except Exception:
                tries = tries - 1
                if tries == 0:
                    raise
                pass
        return weakref.proxy(self._ssh_master)

    def _sanitize_command(self, command, allow_ssh_args):
        """
        Helper method for run_command, which essentially prepares and properly
        escape the command. See run_command() for further description.
        """
        if isinstance(command, basestring):
            if allow_ssh_args:
                return shlex.split(command)
            else:
                return ['--', command]
        # iterable
        elif allow_ssh_args:
            return command
        else:
            return ['--', ' '.join(["'{0}'".format(arg.replace("'", r"'\''"))
                                    for arg in command])]

    def run_command(self, command, flags=[], timeout=None, logged=True,
                    allow_ssh_args=False, **kwargs):
        """
        Execute a 'command' on the current target host using SSH, passing
        'flags' as additional arguments to SSH. The command can be either a
        string or an iterable of strings, whereby if it's the latter, it will
        be joined with spaces and properly shell-escaped.

        If 'allow_ssh_args' is set to True, the specified command may contain
        SSH flags.

        All keyword arguments except timeout are passed as-is to
        nixops.util.logged_exec(), though if you set 'logged' to False, the
        keyword arguments are passed as-is to subprocess.call() and the command
        is executed interactively with no logging.

        'timeout' specifies the SSH connection timeout.
        """
        tries = 5
        if timeout is not None:
            flags = flags + ["-o", "ConnectTimeout={0}".format(timeout)]
            tries = 1
        master = self.get_master(flags, tries)
        flags = flags + self._get_flags()
        if logged:
            flags.append("-x")
        cmd = ["ssh"] + master.opts + flags
        cmd.append(self._get_target())
        cmd += self._sanitize_command(command, allow_ssh_args)
        if logged:
            try:
                return nixops.util.logged_exec(cmd, self._logger, **kwargs)
            except nixops.util.CommandFailed as exc:
                raise SSHCommandFailed(exc.message, exc.exitcode)
        else:
            check = kwargs.pop('check', True)
            res = subprocess.call(cmd, **kwargs)
            if check and res != 0:
                msg = "command ‘{0}’ failed on host ‘{1}’"
                err = msg.format(cmd, self._get_target())
                raise SSHCommandFailed(err, res)
            else:
                return res
