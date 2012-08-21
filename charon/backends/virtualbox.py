# -*- coding: utf-8 -*-

import os
import sys
import time
import shutil
import stat
from charon.backends import MachineDefinition, MachineState
import charon.known_hosts


class VirtualBoxDefinition(MachineDefinition):
    """Definition of a VirtualBox machine."""

    @classmethod
    def get_type(cls):
        return "virtualbox"

    def __init__(self, xml):
        MachineDefinition.__init__(self, xml)
        x = xml.find("attrs/attr[@name='virtualbox']/attrs")
        assert x is not None
        self.base_image = x.find("attr[@name='baseImage']/string").get("value")
        self.memory_size = x.find("attr[@name='memorySize']/int").get("value")
        self.headless = x.find("attr[@name='headless']/bool").get("value") == "true"


class VirtualBoxState(MachineState):
    """State of a VirtualBox machine."""

    @classmethod
    def get_type(cls):
        return "virtualbox"

    def __init__(self, depl, name, log_file=sys.stderr):
        MachineState.__init__(self, depl, name, log_file)
        self._vm_id = None
        self._ipv4 = None
        self._disk = None
        self._disk_attached = False
        self._started = False
        self._headless = False
        self._client_private_key = None
        self._client_public_key = None

    def serialise(self):
        x = MachineState.serialise(self)
        if self._vm_id: x['vmId'] = self._vm_id
        if self._ipv4: x['privateIpv4'] = self._ipv4

        y = {}
        if self._disk: y['disk'] = self._disk
        if self._client_private_key: y['clientPrivateKey'] = self._client_private_key
        if self._client_public_key: y['clientPublicKey'] = self._client_public_key
        y['diskAttached'] = self._disk_attached
        y['started'] = self._started
        y['headless'] = self._headless
        x['virtualbox'] = y

        return x

    def deserialise(self, x):
        MachineState.deserialise(self, x)
        self._vm_id = x.get('vmId', None)
        self._ipv4 = x.get('privateIpv4', None)

        y = x.get('virtualbox')
        self._disk = y.get('disk', None)
        self._disk_attached = y.get('diskAttached', False)
        self._client_private_key = y.get('clientPrivateKey', None)
        self._client_public_key = y.get('clientPublicKey', None)
        self._started = y.get('started', False)
        self._headless = y.get('headless', False)

    def get_ssh_name(self):
        assert self._ipv4
        return self._ipv4

    def get_ssh_flags(self):
        key_file = "{0}/id_charon-{1}".format(self.depl.tempdir, self.name)
        if not os.path.exists(key_file):
            with os.fdopen(os.open(key_file, os.O_CREAT | os.O_WRONLY, 0600), "w") as f:
                f.write(self._client_private_key)
        return ["-o", "StrictHostKeyChecking=no", "-i", key_file]

    def get_physical_spec(self, machines):
        return ['    require = [ <charon/virtualbox-image-charon.nix> ];']

    @property
    def vm_id(self):
        return self._vm_id

    @property
    def private_ipv4(self):
        return self._ipv4


    def address_to(self, m):
        if isinstance(m, VirtualBoxState):
            return m._ipv4
        return MachineState.address_to(self, m)


    def _get_vm_info(self):
        '''Return the output of ‘VBoxManage showvminfo’ in a dictionary.'''
        lines = self._logged_exec(
            ["VBoxManage", "showvminfo", "--machinereadable", self._vm_id],
            capture_stdout=True, check=False).splitlines()
        # We ignore the exit code, because it may be 1 while the VM is
        # shutting down (even though the necessary info is returned on
        # stdout).
        if len(lines) == 0:
            raise Exception("unable to get info on VirtualBox VM ‘{0}’".format(self.name))
        vminfo = {}
        for l in lines:
            (k, v) = l.split("=", 1)
            vminfo[k] = v
        return vminfo


    def _get_vm_state(self):
        '''Return the state ("running", etc.) of a VM.'''
        vminfo = self._get_vm_info()
        if 'VMState' not in vminfo:
            raise Exception("unable to get state of VirtualBox VM ‘{0}’".format(self.name))
        return vminfo['VMState'].replace('"', '')


    def _start(self):
        self._logged_exec(
            ["VBoxManage", "guestproperty", "set", self._vm_id, "/VirtualBox/GuestInfo/Net/1/V4/IP", ''])

        self._logged_exec(
            ["VBoxManage", "guestproperty", "set", self._vm_id, "/VirtualBox/GuestInfo/Charon/ClientPublicKey", self._client_public_key])

        self._logged_exec(["VBoxManage", "startvm", self._vm_id] +
                          (["--type", "headless"] if self._headless else []))

        self._started = True
        self._state = self.STARTING
        self.write()


    def _wait_for_ip(self):
        self.log_start("waiting for IP address...")
        while True:
            res = self._logged_exec(
                ["VBoxManage", "guestproperty", "get", self._vm_id, "/VirtualBox/GuestInfo/Net/1/V4/IP"],
                capture_stdout=True).rstrip()
            if res[0:7] == "Value: ":
                self._ipv4 = res[7:]
                self.log_end(" " + self._ipv4)
                break
            time.sleep(1)
            self.log_continue(".")

        charon.known_hosts.remove(self._ipv4)

        self.write()


    def create(self, defn, check, allow_reboot):
        assert isinstance(defn, VirtualBoxDefinition)

        if self._state != self.UP: check = True

        if not self._vm_id:
            self.log("creating VirtualBox VM...")

            vm_id = "charon-{0}-{1}".format(self.depl.uuid, self.name)

            self._logged_exec(["VBoxManage", "createvm", "--name", vm_id, "--ostype", "Linux", "--register"])

            self._vm_id = vm_id
            self.write()

        if not self._disk:
            vm_dir = os.environ['HOME'] + "/VirtualBox VMs/" + self._vm_id
            if not os.path.isdir(vm_dir):
                raise Exception("can't find directory of VirtualBox VM ‘{0}’".format(self.name))

            disk = vm_dir + "/disk1.vdi"

            base_image = defn.base_image
            if base_image == "drv":
                base_image = self._logged_exec(
                    ["nix-build", "-I", "charon=" + self.depl.expr_path, "--show-trace",
                     "<charon/eval-machine-info.nix>",
                     "--arg", "checkConfigurationOptions", "false",
                     "--arg", "networkExprs", "[ " + " ".join(self.depl.nix_exprs) + " ]",
                     "-A", "nodes." + self.name + ".config.deployment.virtualbox.baseImage",
                     "-o", "{0}/vbox-image-{1}".format(self.depl.tempdir, self.name)],
                    capture_stdout=True).rstrip()

            self._logged_exec(["VBoxManage", "clonehd", base_image, disk])

            self._disk = disk
            self.write()

        if not self._disk_attached:
            self._logged_exec(
                ["VBoxManage", "storagectl", self._vm_id,
                 "--name", "SATA", "--add", "sata", "--sataportcount", "2",
                 "--bootable", "on", "--hostiocache", "on"])

            self._logged_exec(
                ["VBoxManage", "storageattach", self._vm_id,
                 "--storagectl", "SATA", "--port", "0", "--device", "0",
                 "--type", "hdd", "--medium", self._disk])

            self._disk_attached = True
            self.write()

        if check:
            if self._get_vm_state() == 'running':
                self._started = True
            else:
                self.log("VirtualBox VM went down, restarting...")
                self._started = False
                self.write()

        if not self._client_private_key:
            (self._client_private_key, self._client_public_key) = self._create_key_pair()

        if not self._started:
            self._logged_exec(
                ["VBoxManage", "modifyvm", self._vm_id,
                 "--memory", defn.memory_size, "--vram", "10",
                 "--nictype1", "virtio", "--nictype2", "virtio",
                 "--nic2", "hostonly", "--hostonlyadapter2", "vboxnet0",
                 "--nestedpaging", "off"])

            self._headless = defn.headless
            self._start()

        if not self._ipv4 or check:
            self._wait_for_ip()


    def destroy(self):
        if not self.depl.confirm("are you sure you want to destroy VirtualBox VM ‘{0}’?".format(self.name)): return False

        self.log("destroying VirtualBox VM...")

        if self._get_vm_state() == 'running':
            self._logged_exec(["VBoxManage", "controlvm", self._vm_id, "poweroff"], check=False)

        while self._get_vm_state() not in ['poweroff', 'aborted']:
            time.sleep(1)

        time.sleep(1) # hack to work around "machine locked" errors

        self._logged_exec(["VBoxManage", "unregistervm", "--delete", self._vm_id])

        return True


    def stop(self):
        if self._get_vm_state() != 'running': return

        self.log_start("shutting down... ")

        self.run_command("poweroff &")
        self._state = self.STOPPING
        self.write()

        while True:
            state = self._get_vm_state()
            self.log_continue("({0}) ".format(state))
            if state == 'poweroff': break
            time.sleep(1)

        self.log_end("")

        self._started = False
        self._state = self.STOPPED
        self.write()


    def start(self):
        if self._get_vm_state() == 'running': return
        self.log("restarting...")

        prev_ipv4 = self._ipv4

        self._start()
        self._wait_for_ip()

        if prev_ipv4 != self._ipv4:
            self.warn("IP address has changed, you may need to run ‘charon deploy’")

        self.wait_for_ssh(check=True)


    def check(self):
        old_state = self._state
        state = self._get_vm_state()
        self.log("VM state is ‘{0}’".format(state))
        if state == "poweroff" or state == "aborted":
            self._state = self.STOPPED
        elif state == "running":
            MachineState.check(self)
        else:
            self._state = self.UNKNOWN
        if old_state != self._state:
            self.write()
