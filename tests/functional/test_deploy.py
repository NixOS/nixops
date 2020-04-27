from typing import Generator, Optional, Dict, List, Union
from functools import lru_cache
import subprocess
import tempfile
import warnings
import textwrap
import os.path
import signal
import shutil
import glob
import time
import json
import stat
import os


CWD = os.path.dirname(os.path.abspath(__file__))


@lru_cache()
def get_container_image() -> str:
    image_name: str = json.loads(
        subprocess.check_output(
            [
                "nix-instantiate",
                "--strict",
                os.path.join(CWD, "container"),
                "--eval",
                "--json",
                "-A",
                "image",
            ]
        )
    )

    image_id = (
        subprocess.check_output(["docker", "images", "-q", image_name]).decode().strip()
    )
    if image_id:
        return image_id

    warnings.warn("Building NixOS container, this may take some time.")

    store_path: str = subprocess.run(
        [
            "nix-build",
            "--show-trace",
            "--no-out-link",
            os.path.join(CWD, "container"),
            "-A",
            "tarball",
        ],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.decode().strip()

    image_file: str = glob.glob(
        os.path.join(store_path, "tarball/nixos-system-*.tar.xz")
    )[0]

    return (
        subprocess.check_output(["docker", "import", image_file, image_name])
        .decode()
        .strip()
    )


class Container:

    name: str
    image_id: str
    container_id: Optional[str]
    ssh_port: int
    hostname: str
    env: Dict[str, str]

    def __init__(self, name: str, ssh_port: int, image_id: str):
        self.name = name
        self.container_id = None
        self.image_id = image_id
        self._process = None
        self.ssh_port = ssh_port
        self.hostname = "127.0.0.1"
        self.user = "root"
        self.env = {}

    @property
    def started(self) -> bool:
        return self.container_id is not None

    def run(self):
        process = subprocess.run(
            [
                "docker",
                "run",
                "--privileged",
                f"--publish={self.ssh_port}:22",
                "-it",
                "--detach",
                self.image_id,
                "/init",
            ],
            check=True,
            stdout=subprocess.PIPE,
        )
        self.container_id = process.stdout.decode().strip()

    def wait_for_ssh(self, timeout=60):
        timeout = timeout * 10
        while True:
            try:
                subprocess.check_output(
                    [
                        "ssh",
                        "-o",
                        "StrictHostKeyChecking=accept-new",
                        f"{self.user}@{self.hostname}",
                        "-p",
                        str(self.ssh_port),
                        "true",
                    ],
                    env=self.env if self.env else None,
                )
            except Exception as e:
                if timeout == 0:
                    raise e
                time.sleep(0.1)
                timeout -= 1
            else:
                break

    def stop(self):
        if not self.container_id:
            return
        subprocess.run(["docker", "kill", self.container_id])

    def destroy(self):
        if not self.container_id:
            return
        self.stop()
        subprocess.run(["docker", "rm", "-f", self.container_id])


class Deployment:
    def __init__(self, deployment_file: str):
        self._env: Dict[str, str] = dict(os.environ)

        hosts = set(
            json.loads(
                subprocess.check_output(
                    [
                        "nix-instantiate",
                        "--json",
                        "--eval",
                        "--expr",
                        f"builtins.attrNames (import {deployment_file})",
                    ]
                )
            )
        )
        hosts.remove("network")

        self._agent_pid: Optional[int] = None
        self.temp_path = tempfile.TemporaryDirectory()

        self._deployment_file: str = deployment_file

        self.setup_nixops_env()

        self.setup_fake_ssh()
        self.start_ssh_agent()

        self._containers: Dict[str, Container] = {}
        image_id = get_container_image()
        for host in hosts:
            ssh_port = int(
                self.run_command(
                    ["nixops", "show-option", host, "deployment.targetPort"],
                    stdout=subprocess.PIPE,
                ).stdout
            )
            c = Container(name=host, ssh_port=ssh_port, image_id=image_id)
            c.env = self._env
            self._containers[c.name] = c

    def start_ssh_agent(self):
        if self._agent_pid:
            raise ValueError("SSH agent already started")

        agent = json.loads(
            subprocess.check_output(
                'eval $(ssh-agent -s | grep -v "Agent pid") && echo "{\\"SSH_AUTH_SOCK\\": \\"$SSH_AUTH_SOCK\\", \\"SSH_AGENT_PID\\": \\"$SSH_AGENT_PID\\"}"',
                shell=True,
            )
        )
        self._agent_pid = int(agent["SSH_AGENT_PID"])
        self._env.update(agent)

        key_file: str = os.path.join(CWD, "snakeoil/id_ed25519")

        subprocess.check_output(["chmod", "600", key_file])
        subprocess.check_output(["ssh-add", key_file], env=self._env)

    def setup_nixops_env(self):
        tmpdir = self.temp_path.name
        self._env["NIXOPS_STATE"] = os.path.join(tmpdir, "nixops_state.nixops")
        self.run_command(["nixops", "create", self._deployment_file])

    def setup_fake_ssh(self):
        tmpdir = self.temp_path.name

        known_hosts = os.path.join(tmpdir, "known_hosts")

        bin_path = os.path.join(tmpdir, "bin")
        os.mkdir(bin_path)

        ssh_bin = os.path.join(bin_path, "ssh")
        ssh_real = shutil.which("ssh")
        with open(ssh_bin, mode="w") as f:
            f.write("#!/usr/bin/env sh\n")
            f.write(f'exec {ssh_real} -o UserKnownHostsFile={known_hosts} "$@"\n')

        st = os.stat(ssh_bin)
        os.chmod(ssh_bin, st.st_mode | stat.S_IEXEC)

        self._env["PATH"] = f"{bin_path}:" + self._env["PATH"]

    def run_command(self, *args, check=True, **kwargs) -> subprocess.CompletedProcess:
        """Run a command within the Deployment environment"""
        kwargs["env"] = self._env
        kwargs["check"] = check
        return subprocess.run(*args, **kwargs)

    def stop_ssh_agent(self):
        if self._agent_pid:
            os.killpg(os.getpgid(self._agent_pid), signal.SIGTERM)

    def __enter__(self):
        for c in self._containers.values():
            c.run()

        for c in self._containers.values():
            c.wait_for_ssh()

        return self

    def __exit__(self, type, value, traceback):
        self.stop_ssh_agent()

        for c in self._containers.values():
            c.destroy()


class TestContainerNetwork:

    # EVAL_EXPR = textwrap.dedent("""
    # (file: let
    #   f = (import file).network.__test;
    #   pkgs = import <nixpkgs> {};
    #   jobs = f { inherit pkgs; };
    # in pkgs.writeText "manifest.json" (builtins.toJSON jobs))
    # """).replace('\n', ' ')
    EVAL_EXPR = textwrap.dedent(
        """
    (file: let
      jobs = (import file).network.__test;
    in (import <nixpkgs> {}).writeText "manifest.json" (builtins.toJSON jobs))
    """
    ).replace("\n", " ")

    def __init__(self):
        get_container_image()

    def eval(self, network_file):
        p = subprocess.run(
            ["nix-build", "--no-out-link", "-E", self.EVAL_EXPR + f" {network_file}",],
            check=True,
            stdout=subprocess.PIPE,
        )

        with open(p.stdout.decode().strip()) as f:
            return json.load(f)

    def execute(self, name: str, network_path: str, data: Dict):
        with Deployment(deployment_file=network_path,) as d:
            for cmd in data["commands"]:
                if len(cmd.keys()) > 1:
                    raise ValueError("Multiple commands in one attrset not allowed")
                elif "nixops" in cmd:
                    c: Union[List[str], str] = cmd["nixops"]
                    args: List[str] = ["nixops"]
                    if isinstance(c, list):
                        args.extend(c)
                    else:
                        args.append(c)
                    d.run_command(args)
                else:
                    raise ValueError("Unhandled cmd ", cmd)

    def test_networks(self):
        network_dir = os.path.join(CWD, "networks")
        for network in os.listdir(network_dir):
            network_path = os.path.join(network_dir, network, "network.nix")
            test_json = self.eval(network_path)
            for test, attrs in test_json.items():
                yield self.execute, network, network_path, attrs
