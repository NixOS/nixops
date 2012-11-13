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

    state = charon.util.attr_property("state", MachineState.MISSING, int) # override
    private_ipv4 = charon.util.attr_property("privateIpv4", None)
    disk = charon.util.attr_property("virtualbox.disk", None)
    disk_attached = charon.util.attr_property("virtualbox.diskAttached", False, bool)
    _client_private_key = charon.util.attr_property("virtualbox.clientPrivateKey", None)
    _client_public_key = charon.util.attr_property("virtualbox.clientPublicKey", None)
    _headless = charon.util.attr_property("virtualbox.headless", False, bool)

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        self._disk_attached = False

    @property
    def resource_id(self):
        return self.vm_id

    def get_ssh_name(self):
        assert self.private_ipv4
        return self.private_ipv4

    def get_ssh_flags(self):
        key_file = "{0}/id_charon-{1}".format(self.depl.tempdir, self.name)
        if not os.path.exists(key_file):
            with os.fdopen(os.open(key_file, os.O_CREAT | os.O_WRONLY, 0600), "w") as f:
                f.write(self._client_private_key)
        return ["-o", "StrictHostKeyChecking=no", "-i", key_file]

    def get_physical_spec(self, machines):
        return ['    require = [ <charon/virtualbox-image-charon.nix> ];']


    def address_to(self, m):
        if isinstance(m, VirtualBoxState):
            return m.private_ipv4
        return MachineState.address_to(self, m)


    def _get_vm_info(self):
        '''Return the output of ‘VBoxManage showvminfo’ in a dictionary.'''
        lines = self._logged_exec(
            ["VBoxManage", "showvminfo", "--machinereadable", self.vm_id],
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
            ["VBoxManage", "guestproperty", "set", self.vm_id, "/VirtualBox/GuestInfo/Net/1/V4/IP", ''])

        self._logged_exec(
            ["VBoxManage", "guestproperty", "set", self.vm_id, "/VirtualBox/GuestInfo/Charon/ClientPublicKey", self._client_public_key])

        self._logged_exec(["VBoxManage", "startvm", self.vm_id] +
                          (["--type", "headless"] if self._headless else []))

        self.state = self.STARTING


    def _update_ip(self):
        res = self._logged_exec(
            ["VBoxManage", "guestproperty", "get", self.vm_id, "/VirtualBox/GuestInfo/Net/1/V4/IP"],
            capture_stdout=True).rstrip()
        if res[0:7] != "Value: ": return
        self.private_ipv4 = res[7:]


    def _wait_for_ip(self):
        self.log_start("waiting for IP address...")
        while True:
            self._update_ip()
            if self.private_ipv4 != None: break
            time.sleep(1)
            self.log_continue(".")
        self.log_end(" " + self.private_ipv4)
        charon.known_hosts.remove(self.private_ipv4)


    def create(self, defn, check, allow_reboot):
        assert isinstance(defn, VirtualBoxDefinition)

        if self.state != self.UP or check: self.check()

        self.set_common_state(defn)

        if not self.vm_id:
            self.log("creating VirtualBox VM...")
            vm_id = "charon-{0}-{1}".format(self.depl.uuid, self.name)
            self._logged_exec(["VBoxManage", "createvm", "--name", vm_id, "--ostype", "Linux", "--register"])
            self.vm_id = vm_id
            self.state = self.STOPPED

        if not self.disk:
            vm_dir = os.environ['HOME'] + "/VirtualBox VMs/" + self.vm_id
            if not os.path.isdir(vm_dir):
                raise Exception("can't find directory of VirtualBox VM ‘{0}’".format(self.name))

            disk = vm_dir + "/disk1.vdi"

            base_image = defn.base_image
            if base_image == "drv":
                # FIXME: move this to deployment.py.
                base_image = self._logged_exec(
                    ["nix-build"]
                    + self.depl._eval_flags(self.depl.nix_exprs) +
                    ["--arg", "checkConfigurationOptions", "false",
                     "-A", "nodes." + self.name + ".config.deployment.virtualbox.baseImage",
                     "-o", "{0}/vbox-image-{1}".format(self.depl.tempdir, self.name)],
                    capture_stdout=True).rstrip()

            self._logged_exec(["VBoxManage", "clonehd", base_image, disk])

            self.disk = disk

        if not self.disk_attached:
            self._logged_exec(
                ["VBoxManage", "storagectl", self.vm_id,
                 "--name", "SATA", "--add", "sata", "--sataportcount", "2",
                 "--bootable", "on", "--hostiocache", "on"])

            self._logged_exec(
                ["VBoxManage", "storageattach", self.vm_id,
                 "--storagectl", "SATA", "--port", "0", "--device", "0",
                 "--type", "hdd", "--medium", self.disk])

            self.disk_attached = True

        if not self._client_private_key:
            (self._client_private_key, self._client_public_key) = charon.util.create_key_pair()

        if not self.started:
            self._logged_exec(
                ["VBoxManage", "modifyvm", self.vm_id,
                 "--memory", defn.memory_size, "--vram", "10",
                 "--nictype1", "virtio", "--nictype2", "virtio",
                 "--nic2", "hostonly", "--hostonlyadapter2", "vboxnet0",
                 "--nestedpaging", "off"])

            self._headless = defn.headless
            self._start()

        if not self.private_ipv4 or check:
            self._wait_for_ip()


    def destroy(self):
        if not self.vm_id: return True

        if not self.depl.confirm("are you sure you want to destroy VirtualBox VM ‘{0}’?".format(self.name)): return False

        self.log("destroying VirtualBox VM...")

        if self._get_vm_state() == 'running':
            self._logged_exec(["VBoxManage", "controlvm", self.vm_id, "poweroff"], check=False)

        while self._get_vm_state() not in ['poweroff', 'aborted']:
            time.sleep(1)

        self.state = self.STOPPED

        time.sleep(1) # hack to work around "machine locked" errors

        self._logged_exec(["VBoxManage", "unregistervm", "--delete", self.vm_id])

        return True


    def stop(self):
        if self._get_vm_state() != 'running': return

        self.log_start("shutting down... ")

        self.run_command("poweroff &")
        self.state = self.STOPPING

        while True:
            state = self._get_vm_state()
            self.log_continue("({0}) ".format(state))
            if state == 'poweroff': break
            time.sleep(1)

        self.log_end("")

        self.state = self.STOPPED


    def start(self):
        if self._get_vm_state() == 'running': return
        self.log("restarting...")

        prev_ipv4 = self.private_ipv4

        self._start()
        self._wait_for_ip()

        if prev_ipv4 != self.private_ipv4:
            self.warn("IP address has changed, you may need to run ‘charon deploy’")

        self.wait_for_ssh(check=True)


    def check(self):
        if not self.vm_id: return
        state = self._get_vm_state()
        self.log("VM state is ‘{0}’".format(state))
        if state == "poweroff" or state == "aborted":
            self.state = self.STOPPED
        elif state == "running":
            self._update_ip()
            MachineState.check(self)
        else:
            self.state = self.UNKNOWN
