# -*- coding: utf-8 -*-

import os
import sys
import time
import shutil
import stat
from charon.backends import MachineDefinition, MachineState
import charon.known_hosts


sata_ports = 8


class VirtualBoxDefinition(MachineDefinition):
    """Definition of a VirtualBox machine."""

    @classmethod
    def get_type(cls):
        return "virtualbox"

    def __init__(self, xml):
        MachineDefinition.__init__(self, xml)
        x = xml.find("attrs/attr[@name='virtualbox']/attrs")
        assert x is not None
        self.memory_size = x.find("attr[@name='memorySize']/int").get("value")
        self.headless = x.find("attr[@name='headless']/bool").get("value") == "true"

        def f(xml):
            return {'port': int(xml.find("attrs/attr[@name='port']/int").get("value")),
                    'size': int(xml.find("attrs/attr[@name='size']/int").get("value")),
                    'baseImage': xml.find("attrs/attr[@name='baseImage']/string").get("value")}

        self.disks = {k.get("name"): f(k) for k in x.findall("attr[@name='disks']/attrs/attr")}


class VirtualBoxState(MachineState):
    """State of a VirtualBox machine."""

    @classmethod
    def get_type(cls):
        return "virtualbox"

    state = charon.util.attr_property("state", MachineState.MISSING, int) # override
    private_ipv4 = charon.util.attr_property("privateIpv4", None)
    disks = charon.util.attr_property("virtualbox.disks", {}, 'json')
    _client_private_key = charon.util.attr_property("virtualbox.clientPrivateKey", None)
    _client_public_key = charon.util.attr_property("virtualbox.clientPublicKey", None)
    _headless = charon.util.attr_property("virtualbox.headless", False, bool)
    sata_controller_created = charon.util.attr_property("virtualbox.sataControllerCreated", False, bool)

    # Obsolete.
    disk = charon.util.attr_property("virtualbox.disk", None)
    disk_attached = charon.util.attr_property("virtualbox.diskAttached", False, bool)

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
        if not self._ssh_private_key_file:
            self.write_ssh_private_key(self._client_private_key)
        return ["-o", "StrictHostKeyChecking=no", "-i", self._ssh_private_key_file]

    def get_physical_spec(self):
        return ['    require = [ <charon/virtualbox-image-charon.nix> ];']


    def address_to(self, m):
        if isinstance(m, VirtualBoxState):
            return m.private_ipv4
        return MachineState.address_to(self, m)


    def has_really_fast_connection(self):
        return True


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


    def _update_disk(self, name, state):
        disks = self.disks
        if state == None:
            disks.pop(name, None)
        else:
            disks[name] = state
        self.disks = disks


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

        # Backwards compatibility.
        if self.disk:
            with self.depl._db:
                self._update_disk("disk1", {"created": True, "path": self.disk,
                                            "attached": self.disk_attached,
                                            "port": 0})
                self.disk = None
                self.sata_controller_created = self.disk_attached
                self.disk_attached = False

        # Create the SATA controller.
        if not self.sata_controller_created:
            self._logged_exec(
                ["VBoxManage", "storagectl", self.vm_id,
                 "--name", "SATA", "--add", "sata", "--sataportcount", int(sata_ports),
                 "--bootable", "on", "--hostiocache", "on"])
            self.sata_controller_created = True

        vm_dir = os.environ['HOME'] + "/VirtualBox VMs/" + self.vm_id
        if not os.path.isdir(vm_dir):
            raise Exception("can't find directory of VirtualBox VM ‘{0}’".format(self.name))

        # Create missing disks.
        for disk_name, disk_def in defn.disks.items():
            disk_state = self.disks.get(disk_name, {})

            if not disk_state.get('created', False):
                self.log("creating disk ‘{0}’...".format(disk_name))

                disk_path = "{0}/{1}.vdi".format(vm_dir, disk_name)

                base_image = disk_def.get('baseImage')
                if base_image:
                    # Clone an existing disk image.
                    if base_image == "drv":
                        # FIXME: move this to deployment.py.
                        base_image = self._logged_exec(
                            ["nix-build"]
                            + self.depl._eval_flags(self.depl.nix_exprs) +
                            ["--arg", "checkConfigurationOptions", "false",
                             "-A", "nodes.{0}.config.deployment.virtualbox.disks.{1}.baseImage".format(self.name, disk_name),
                             "-o", "{0}/vbox-image-{1}".format(self.depl.tempdir, self.name)],
                            capture_stdout=True).rstrip()
                    self._logged_exec(["VBoxManage", "clonehd", base_image, disk_path])
                else:
                    # Create an empty disk.
                    if disk_def['size'] <= 0:
                        raise Exception("size of VirtualBox disk ‘{0}’ must be positive".format(disk_name))
                    self._logged_exec(["VBoxManage", "createhd", "--filename", disk_path, "--size", str(disk_def['size'])])
                    disk_state['size'] = disk_def['size']

                disk_state['created'] = True
                disk_state['path'] = disk_path
                self._update_disk(disk_name, disk_state)

            if not disk_state.get('attached', False):
                self.log("attaching disk ‘{0}’...".format(disk_name))

                if disk_def['port'] >= sata_ports:
                    raise Exception("SATA port number {0} of disk ‘{1}’ exceeds maximum ({2})".format(disk_def['port'], disk_name, sata_ports))

                for disk_name2, disk_state2 in self.disks.items():
                    if disk_name != disk_name2 and disk_state2.get('attached', False) and \
                            disk_state2['port'] == disk_def['port']:
                        raise Exception("cannot attach disks ‘{0}’ and ‘{1}’ to the same SATA port on VirtualBox machine ‘{2}’".format(disk_name, disk_name2, self.name))

                self._logged_exec(
                    ["VBoxManage", "storageattach", self.vm_id,
                     "--storagectl", "SATA", "--port", str(disk_def['port']), "--device", "0",
                     "--type", "hdd", "--medium", disk_state['path']])
                disk_state['attached'] = True
                disk_state['port'] = disk_def['port']
                self._update_disk(disk_name, disk_state)

        # FIXME: warn about changed disk attributes (like size).  Or
        # even better, handle them (e.g. resize existing disks).

        # Destroy obsolete disks.
        for disk_name, disk_state in self.disks.items():
            if disk_name not in defn.disks:
                if not self.depl.confirm("are you sure you want to destroy disk ‘{0}’ of VirtualBox instance ‘{1}’?".format(disk_name, self.name)):
                    raise Exception("not destroying VirtualBox disk ‘{0}’".format(disk_name))
                self.log("destroying disk ‘{0}’".format(disk_name))

                if disk_state.get('attached', False):
                    # FIXME: only do this if the device is actually
                    # attached (and remove check=False).
                    self._logged_exec(
                        ["VBoxManage", "storageattach", self.vm_id,
                         "--storagectl", "SATA", "--port", str(disk_state['port']), "--device", "0",
                         "--type", "hdd", "--medium", "none"], check=False)
                    disk_state['attached'] = False
                    disk_state.pop('port')
                    self._update_disk(disk_name, disk_state)

                if disk_state['created']:
                    self._logged_exec(
                        ["VBoxManage", "closemedium", "disk", disk_state['path'], "--delete"])

                self._update_disk(disk_name, None)

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
