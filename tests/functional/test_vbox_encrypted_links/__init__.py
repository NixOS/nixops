from nose import tools
from nixops.ssh_util import SSHCommandFailed
from nixops.util import root_dir
from itertools import product
from parameterized import parameterized

from tests.functional.shared.deployment_run_command import deployment_run_command
from tests.functional.shared.create_deployment import create_deployment
from tests.functional.shared.using_state_file import using_state_file

from os import path
from nose import tools, SkipTest
from tests.functional import generic_deployment_test
from nixops.ssh_util import SSHCommandFailed
from nixops.util import devnull
import sys
import time
import signal
import subprocess

parent_dir = path.dirname(__file__)

logical_spec = '{}/encrypted-links.nix'.format(parent_dir)

@parameterized(
    ['json', 'nixops']
)
def test_vbox_encrypted_links(state_extension):
    if subprocess.call(["VBoxManage", "--version"],
                       stdout=devnull,
                       stderr=devnull) != 0:
        raise SkipTest("VirtualBox is not available")

    with using_state_file(state_extension) as state:
        deployment = create_deployment(state, [logical_spec])

        deployment.debug = True
        deployment.deploy()

        # !!! Shouldn't need this, instead the encrypted links target
        # should wait until the link is active...
        time.sleep(1)
        ping(deployment, "machine1", "machine2")
        ping(deployment, "machine2", "machine1")

        deployment.machines["machine1"].run_command("systemctl stop encrypted-links.target")

        with tools.assert_raises(SSHCommandFailed):
            ping(deployment, "machine1", "machine2")

        with tools.assert_raises(SSHCommandFailed):
            ping(deployment, "machine2", "machine1")


# Helpers

def ping(deployment, machine1, machine2):
    deployment.machines[machine1].run_command("ping -c1 {0}-encrypted".format(machine2))
