# -*- coding: utf-8 -*-

import os
import sys
import time
import shutil
import stat
from nixops.backends import MachineDefinition, MachineState
from nixops.nix_expr import RawValue
import nixops.known_hosts
from distutils import spawn

sata_ports = 8


class VirtualBoxDefinition(MachineDefinition):
    """Definition of a VirtualBox machine."""

    @classmethod
    def get_type(cls):
        return "virtualbox"

    def __init__(self, xml, config):
        MachineDefinition.__init__(self, xml, config)


class VirtualBoxState(MachineState):
    """State of a VirtualBox machine."""

    @classmethod
    def get_type(cls):
        return "virtualbox"

    state = nixops.util.attr_property("state", MachineState.MISSING, int) # override
    private_ipv4 = nixops.util.attr_property("privateIpv4", None)
    disks = nixops.util.attr_property("virtualbox.disks", {}, 'json')
    _client_private_key = nixops.util.attr_property("virtualbox.clientPrivateKey", None)
    _client_public_key = nixops.util.attr_property("virtualbox.clientPublicKey", None)
    _headless = nixops.util.attr_property("virtualbox.headless", False, bool)
    sata_controller_created = nixops.util.attr_property("virtualbox.sataControllerCreated", False, bool)
    public_host_key = nixops.util.attr_property("virtualbox.publicHostKey", None)
    private_host_key = nixops.util.attr_property("virtualbox.privateHostKey", None)
    shared_folders = nixops.util.attr_property("virtualbox.sharedFolders", {}, 'json')

    # Obsolete.
    disk = nixops.util.attr_property("virtualbox.disk", None)
    disk_attached = nixops.util.attr_property("virtualbox.diskAttached", False, bool)

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        self._disk_attached = False

    @property
    def resource_id(self):
        return self.vm_id

    def get_ssh_name(self):
        assert self.private_ipv4
        return self.private_ipv4

    def get_ssh_private_key_file(self):
        return self._ssh_private_key_file or self.write_ssh_private_key(self._client_private_key)

    def get_ssh_flags(self, *args, **kwargs):
        super_flags = super(VirtualBoxState, self).get_ssh_flags(*args, **kwargs)
        return super_flags + ["-i", self.get_ssh_private_key_file()]

    def get_physical_spec(self):
        return {'imports': [RawValue('<nixops/virtualbox-image-nixops.nix>')]}


    def address_to(self, m):
        if isinstance(m, VirtualBoxState):
            return m.private_ipv4
        return MachineState.address_to(self, m)

    @property
    def _vbox_version(self):
        v = getattr(self, '_vbox_version_obj', None)
        if v is None:
            try:
                v = self._logged_exec(["VBoxManage", "--version"], capture_stdout=True, check=False).strip().split('.')
            except AttributeError:
                v = False
            self._vbox_version_obj = v
        return v

    @property
    def _vbox_flag_sataportcount(self):
        v = self._vbox_version
        if (int(v[0]) >= 5) or (int(v[0]) == 4 and int(v[1]) >= 3):
            return '--portcount'
        else:
            return'--sataportcount'

    def _get_vm_info(self, can_fail=False):
        '''Return the output of ‘VBoxManage showvminfo’ in a dictionary.'''
        lines = self._logged_exec(
            ["VBoxManage", "showvminfo", "--machinereadable", self.vm_id],
            capture_stdout=True, check=False).splitlines()
        # We ignore the exit code, because it may be 1 while the VM is
        # shutting down (even though the necessary info is returned on
        # stdout).
        if len(lines) == 0:
            if can_fail:
                return None
            raise Exception("unable to get info on VirtualBox VM ‘{0}’".format(self.name))
        vminfo = {}
        for l in lines:
            (k, v) = l.split("=", 1)
            vminfo[k] = v if not len(v) or v[0]!='"' else v[1:-1]
        return vminfo


    def _get_vm_state(self, can_fail=False):
        '''Return the state ("running", etc.) of a VM.'''
        vminfo = self._get_vm_info(can_fail)
        if not vminfo and can_fail:
            return None
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
        new_address = res[7:]
        nixops.known_hosts.update(self.private_ipv4, new_address, self.public_host_key)
        self.private_ipv4 = new_address


    def _update_disk(self, name, state):
        disks = self.disks
        if state == None:
            disks.pop(name, None)
        else:
            disks[name] = state
        self.disks = disks


    def _update_shared_folder(self, name, state):
        shared_folders = self.shared_folders
        if state == None:
            shared_folders.pop(name, None)
        else:
            shared_folders[name] = state
        self.shared_folders = shared_folders


    def _wait_for_ip(self):
        self.log_start("waiting for IP address...")
        while True:
            self._update_ip()
            if self.private_ipv4 != None: break
            time.sleep(1)
            self.log_continue(".")
        self.log_end(" " + self.private_ipv4)


    def create(self, defn, check, allow_reboot, allow_recreate):
        assert isinstance(defn, VirtualBoxDefinition)

        if self.state != self.UP or check: self.check()

        self.set_common_state(defn)

        # check if VBoxManage is available in PATH
        if not spawn.find_executable("VBoxManage"):
            raise Exception("VirtualBox is not installed, please install VirtualBox")

        if not self.vm_id:
            self.log("creating VirtualBox VM...")
            vm_id = "nixops-{0}-{1}".format(self.depl.uuid, self.name)
            self._logged_exec(["VBoxManage", "createvm", "--name", vm_id, "--ostype", "Linux26_64", "--register"])
            self.vm_id = vm_id
            self.state = self.STOPPED

        # Generate a public/private host key.
        if not self.public_host_key:
            (private, public) = nixops.util.create_key_pair()
            with self.depl._db:
                self.public_host_key = public
                self.private_host_key = private

        self._logged_exec(
            ["VBoxManage", "guestproperty", "set", self.vm_id, "/VirtualBox/GuestInfo/NixOps/PrivateHostEd25519Key", self.private_host_key])

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
                 "--name", "SATA", "--add", "sata", self._vbox_flag_sataportcount, str(sata_ports),
                 "--bootable", "on", "--hostiocache", "on"])
            self.sata_controller_created = True

        vm_dir = os.path.dirname(self._get_vm_info()['CfgFile'])

        if not os.path.isdir(vm_dir):
            raise Exception("can't find directory of VirtualBox VM ‘{0}’".format(self.name))


        # Create missing shared folders
        for sf_name, sf_def in defn.config["virtualbox"]["sharedFolders"].items():
            sf_state = self.shared_folders.get(sf_name, {})

            if not sf_state.get('added', False):
                self.log("adding shared folder ‘{0}’...".format(sf_name))
                host_path = sf_def.get('hostPath')
                read_only = sf_def.get('readOnly')

                vbox_opts = ["VBoxManage", "sharedfolder", "add", self.vm_id,
                             "--name", sf_name, "--hostpath", host_path]

                if read_only:
                    vbox_opts.append("--readonly")

                self._logged_exec(vbox_opts)

                sf_state['added'] = True
                self._update_shared_folder(sf_name, sf_state)

        # Remove obsolete shared folders
        for sf_name, sf_state in self.shared_folders.items():
            if sf_name not in defn.config["virtualbox"]["sharedFolders"]:
                if not self.started:
                    self.log("removing shared folder ‘{0}’".format(sf_name))

                    if sf_state['added']:
                        vbox_opts = ["VBoxManage", "sharedfolder", "remove", self.vm_id,
                                     "--name", sf_name]
                        self._logged_exec(vbox_opts)

                    self._update_shared_folder(sf_name, None)
                else:
                    self.warn("skipping removal of shared folder ‘{0}’ since VirtualBox machine is running".format(sf_name))



        # Create missing disks.
        for disk_name, disk_def in defn.config["virtualbox"]["disks"].items():
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
                             "-A", 'nodes."{0}".config.deployment.virtualbox.disks.{1}.baseImage'.format(self.name, disk_name),
                             "-o", "{0}/vbox-image-{1}".format(self.depl.tempdir, self.name)],
                            capture_stdout=True).rstrip()
                    self._logged_exec(["VBoxManage", "clonehd", base_image, disk_path, "--format", "VDI"])
                    if disk_def['size'] != 0:
                        self._logged_exec(["VBoxManage", "modifyhd", disk_path, "--resize", str(disk_def['size'])])
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
            if disk_name not in defn.config["virtualbox"]["disks"]:
                if not self.depl.logger.confirm("are you sure you want to destroy disk ‘{0}’ of VirtualBox instance ‘{1}’?".format(disk_name, self.name)):
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
            (self._client_private_key, self._client_public_key) = nixops.util.create_key_pair()

        if not self.started:
            modifyvm_args = [
                 "--memory", str(defn.config["virtualbox"]["memorySize"]),
                 "--vram", "10",
                 "--nictype1", "virtio",
                 "--nictype2", "virtio",
                 "--nic2", "hostonly",
                 "--hostonlyadapter2", "vboxnet0",
                 "--nestedpaging", "off",
                 "--paravirtprovider", "kvm"
            ]
            vcpus = defn.config["virtualbox"]["vcpu"]  # None or integer
            if vcpus is not None:
                modifyvm_args.extend(["--cpus", str(vcpus)])
            # Include arbitrary additional arguments
            modifyvm_args.extend(defn.config["virtualbox"]["vmFlags"])
            self._logged_exec(
                ["VBoxManage", "modifyvm", self.vm_id] + modifyvm_args)

            self._headless = defn.config["virtualbox"]["headless"]
            self._start()

        if not self.private_ipv4 or check:
            self._wait_for_ip()


    def destroy(self, wipe=False):
        if not self.vm_id: return True

        if not self.depl.logger.confirm("are you sure you want to destroy VirtualBox VM ‘{0}’?".format(self.name)): return False

        self.log("destroying VirtualBox VM...")

        vmstate = self._get_vm_state(can_fail=True)
        if vmstate is None:
            self.log("VM not found, ignored")
            self.state = self.MISSING
            return True

        if vmstate == 'running':
            self._logged_exec(["VBoxManage", "controlvm", self.vm_id, "poweroff"], check=False)

        while self._get_vm_state() not in ['poweroff', 'aborted']:
            time.sleep(1)

        self.state = self.STOPPED

        time.sleep(1) # hack to work around "machine locked" errors

        nixops.known_hosts.update(self.private_ipv4, None, self.public_host_key)

        self._logged_exec(["VBoxManage", "unregistervm", "--delete", self.vm_id])

        return True


    def stop(self):
        state = self._get_vm_state()

        if state not in ['poweroff', 'aborted']:

            self.log_start("shutting down... ")

            self.run_command("systemctl poweroff", check=False)
            self.state = self.STOPPING

            while True:
                state = self._get_vm_state()
                self.log_continue("[{0}] ".format(state))
                if state == 'poweroff': break
                time.sleep(1)

                self.log_end("")

        self.state = self.STOPPED
        self.ssh_master = None


    def start(self):
        if self._get_vm_state() == 'running': return
        self.log("starting...")

        prev_ipv4 = self.private_ipv4

        self._start()
        self._wait_for_ip()

        self.ssh_pinged = False
        self._ssh_pinged_this_time = False

        if prev_ipv4 != self.private_ipv4:
            self.warn("IP address has changed, you may need to run ‘nixops deploy’")

        self.wait_for_ssh(check=True)


    def _check(self, res):
        if not self.vm_id:
            res.exists = False
            return
        state = self._get_vm_state(can_fail=True)
        if state is None:
            with self.depl._db:
                self.vm_id = None
                self.private_ipv4 = None
                self.sata_controller_created = False
                self.public_host_key = None
                self.private_host_key = None
                self.shared_folders = {}
                self.disks = {}
                self.state = self.MISSING
                return

        res.exists = True
        #self.log("VM state is ‘{0}’".format(state))
        if state == "poweroff" or state == "aborted":
            res.is_up = False
            self.state = self.STOPPED
        elif state == "running":
            res.is_up = True
            self._update_ip()
            MachineState._check(self, res)
        else:
            self.state = self.UNKNOWN
