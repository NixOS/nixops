import os
import subprocess

import nixops.util


class SSHConnectionFailed(Exception):
    pass


class SSHCommandFailed(Exception):
    pass


class SSHMaster(object):
    def __init__(self, tempdir, name, ssh_name, ssh_flags, password=None):
        self._tempdir = tempdir
        self._askpass_helper = None
        self._control_socket = tempdir + "/ssh-master-" + name
        self._ssh_name = ssh_name
        pass_prompts = 0
        kwargs = {}
        additional_opts = []
        if password is not None:
            self._askpass_helper = self._make_askpass_helper()
            newenv = dict(os.environ)
            newenv.update({
                'DISPLAY': ':666',
                'SSH_ASKPASS': self._askpass_helper,
                'NIXOPS_SSH_PASSWORD': password,
            })
            kwargs['env'] = newenv
            kwargs['stdin'] = nixops.util.devnull
            kwargs['preexec_fn'] = os.setsid
            pass_prompts = 1
            additional_opts = ['-oUserKnownHostsFile=/dev/null',
                               '-oStrictHostKeyChecking=no']
        cmd = ["ssh", "-x", "root@" + self._ssh_name, "-S",
               self._control_socket, "-M", "-N", "-f",
               '-oNumberOfPasswordPrompts={0}'.format(pass_prompts),
               '-oServerAliveInterval=60'] + additional_opts
        res = subprocess.call(cmd + ssh_flags, **kwargs)
        if res != 0:
            raise SSHConnectionFailed(
                "unable to start SSH master connection to ‘{0}’".format(name)
            )
        self.opts = ["-S", self._control_socket]

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

    def __del__(self):
        if self._askpass_helper is not None:
            try:
                os.unlink(self._askpass_helper)
            except OSError:
                pass
        subprocess.call(["ssh", "root@" + self._ssh_name, "-S",
                         self._control_socket, "-O", "exit"],
                        stderr=nixops.util.devnull)
