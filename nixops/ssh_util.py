# -*- coding: utf-8 -*-
import atexit
import os
import shlex
import subprocess
import sys
import time
import weakref
from tempfile import mkdtemp
import nixops.util

__all__ = ["SSHConnectionFailed", "SSHCommandFailed", "SSH"]


class SSHConnectionFailed(Exception):
    pass


class SSHCommandFailed(nixops.util.CommandFailed):
    pass


class SSHMaster(object):
    def __init__(self, target, logger, ssh_flags, passwd, user, compress=False):
        self._running = False
        self._tempdir = nixops.util.SelfDeletingDir(mkdtemp(prefix="nixops-ssh-tmp"))
        self._askpass_helper = None
        self._control_socket = self._tempdir + "/master-socket"
        self._ssh_target = target
        pass_prompts = 0 if "-i" in ssh_flags and user is None else 3
        kwargs = {}

        if passwd is not None:
            self._askpass_helper = self._make_askpass_helper()
            newenv = dict(os.environ)
            newenv.update(
                {
                    "DISPLAY": ":666",
                    "SSH_ASKPASS": self._askpass_helper,
                    "NIXOPS_SSH_PASSWORD": passwd,
                }
            )
            kwargs["env"] = newenv
            kwargs["stdin"] = nixops.util.devnull
            kwargs["preexec_fn"] = os.setsid
            pass_prompts = 1

        cmd = (
            [
                "ssh",
                "-x",
                self._ssh_target,
                "-S",
                self._control_socket,
                "-M",
                "-N",
                "-f",
                "-oNumberOfPasswordPrompts={0}".format(pass_prompts),
                "-oServerAliveInterval=60",
                "-oControlPersist=600",
            ]
            + (["-C"] if compress else [])
            + ssh_flags
        )

        res = nixops.util.logged_exec(cmd, logger, **kwargs)
        if res != 0:
            raise SSHConnectionFailed(
                "unable to start SSH master connection to " "‘{0}’".format(target)
            )
        self.opts = ["-oControlPath={0}".format(self._control_socket)]

        timeout = 60.0
        while not self.is_alive():
            if timeout < 0:
                raise SSHConnectionFailed(
                    "could not establish an SSH master socket to "
                    "‘{0}’ within 60 seconds".format(target)
                )
            time.sleep(0.1)
            timeout -= 0.1

        self._running = True

        weakself = weakref.ref(self)

        def maybe_shutdown():
            realself = weakself()
            if realself is not None:
                realself.shutdown()

        atexit.register(maybe_shutdown)

    def is_alive(self):
        """
        Check whether the control socket is still existing.
        """
        return os.path.exists(self._control_socket)

    def _make_askpass_helper(self):
        """
        Create a SSH_ASKPASS helper script, which just outputs the contents of
        the environment variable NIXOPS_SSH_PASSWORD.
        """
        path = os.path.join(self._tempdir, "nixops-askpass-helper")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o700)
        os.write(
            fd,
            """#!{0}
import sys
import os
sys.stdout.write(os.environ['NIXOPS_SSH_PASSWORD'])""".format(
                sys.executable
            ),
        )
        os.close(fd)
        return path

    def shutdown(self):
        """
        Shutdown master process and clean up temporary files.
        """
        if not self._running:
            return
        self._running = False
        subprocess.call(
            ["ssh", self._ssh_target, "-S", self._control_socket, "-O", "exit"],
            stderr=nixops.util.devnull,
        )
        self._tempdir = None

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
        self._compress = False

    def register_host_fun(self, host_fun):
        """
        Register a function which returns the hostname or IP to connect to. The
        function has to require no arguments.
        """
        self._host_fun = host_fun

    def _get_target(self, user=None):
        if self._host_fun is None:
            raise AssertionError("don't know which SSH host to connect to")
        return "{0}@{1}".format("root" if user is None else user, self._host_fun())

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

    def get_master(self, flags=[], timeout=None, user=None):
        """
        Start (if necessary) an SSH master connection to speed up subsequent
        SSH sessions. Returns the SSHMaster instance on success.
        """
        flags = flags + self._get_flags()
        if self._ssh_master is not None:
            master = weakref.proxy(self._ssh_master)
            if master.is_alive():
                return master
            else:
                master.shutdown()

        tries = 5
        if timeout is not None:
            flags = flags + ["-o", "ConnectTimeout={0}".format(timeout)]
            tries = 1

        if self._host_fun() == "localhost":
            tries = 1

        sleep_time = 1
        while True:
            try:
                started_at = time.time()
                self._ssh_master = SSHMaster(
                    self._get_target(user),
                    self._logger,
                    flags,
                    self._get_passwd(),
                    user,
                    compress=self._compress,
                )
                break
            except Exception:
                tries = tries - 1
                if tries == 0:
                    raise
                msg = "could not connect to ‘{0}’, retrying in {1} seconds..."
                self._logger.log(msg.format(self._get_target(user), sleep_time))
                time.sleep(sleep_time)
                sleep_time = sleep_time * 2
                pass

        return weakref.proxy(self._ssh_master)

    @classmethod
    def split_openssh_args(self, args):
        """
        Splits the specified list of arguments into a tuple consisting of the
        list of flags and a list of strings for the actual command.
        """
        non_option_args = "bcDEeFIiLlmOopQRSWw"
        flags = []
        command = list(args)
        while len(command) > 0:
            arg = command.pop(0)
            if arg == "--":
                break
            elif arg.startswith("-"):
                if len(command) > 0 and arg[1] in non_option_args:
                    flags.append(arg)
                    if len(arg) == 2:
                        flags.append(command.pop(0))
                elif len(arg) > 2 and arg[1] != "-":
                    flags.append(arg[:2])
                    command.insert(0, "-" + arg[2:])
                else:
                    flags.append(arg)
            else:
                command.insert(0, arg)
                break
        return (flags, command)

    def _sanitize_command(self, command, allow_ssh_args):
        """
        Helper method for run_command, which essentially prepares and properly
        escape the command. See run_command() for further description.
        """
        if isinstance(command, str):
            if allow_ssh_args:
                return shlex.split(command)
            else:
                return ["--", command]
        # iterable
        elif allow_ssh_args:
            return command
        else:
            return [
                "--",
                " ".join(
                    ["'{0}'".format(arg.replace("'", r"'\''")) for arg in command]
                ),
            ]

    def run_command(
        self,
        command,
        flags=[],
        timeout=None,
        logged=True,
        allow_ssh_args=False,
        user=None,
        **kwargs
    ):
        """
        Execute a 'command' on the current target host using SSH, passing
        'flags' as additional arguments to SSH. The command can be either a
        string or an iterable of strings, whereby if it's the latter, it will
        be joined with spaces and properly shell-escaped.

        If 'allow_ssh_args' is set to True, the specified command may contain
        SSH flags.

        The 'user' argument specifies the remote user to connect as. If unset
        or None, the default is "root".

        All keyword arguments except timeout and user are passed as-is to
        nixops.util.logged_exec(), though if you set 'logged' to False, the
        keyword arguments are passed as-is to subprocess.call() and the command
        is executed interactively with no logging.

        'timeout' specifies the SSH connection timeout.
        """
        master = self.get_master(flags, timeout, user)
        flags = flags + self._get_flags()
        if logged:
            flags.append("-x")
        cmd = ["ssh"] + master.opts + flags
        cmd.append(self._get_target(user))
        cmd += self._sanitize_command(command, allow_ssh_args)
        if logged:
            try:
                return nixops.util.logged_exec(cmd, self._logger, **kwargs)
            except nixops.util.CommandFailed as exc:
                raise SSHCommandFailed(exc.message, exc.exitcode)
        else:
            check = kwargs.pop("check", True)
            res = subprocess.call(cmd, **kwargs)
            if check and res != 0:
                msg = "command ‘{0}’ failed on host ‘{1}’"
                err = msg.format(cmd, self._get_target(user))
                raise SSHCommandFailed(err, res)
            else:
                return res

    def enable_compression(self):
        self._compress = True
