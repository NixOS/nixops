# -*- coding: utf-8 -*-

import os
import sys
import subprocess
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
        self._base_image = x.find("attr[@name='baseImage']/string").get("value")

    def make_state():
        return MachineState()


class VirtualBoxState(MachineState):
    """State of a VirtualBox machine."""

    @classmethod
    def get_type(cls):
        return "virtualbox"
    
    def __init__(self, depl, name):
        MachineState.__init__(self, depl, name)
        self._vm_id = None
        self._ipv4 = None
        self._disk = None
        self._disk_attached = False
        self._started = False
        
    def serialise(self):
        x = MachineState.serialise(self)
        if self._vm_id: x['vmId'] = self._vm_id
        if self._ipv4: x['privateIpv4'] = self._ipv4

        y = {}
        if self._disk: y['disk'] = self._disk
        y['diskAttached'] = self._disk_attached
        y['started'] = self._started
        x['virtualbox'] = y
        
        return x

    def deserialise(self, x):
        MachineState.deserialise(self, x)
        self._vm_id = x.get('vmId', None)
        self._ipv4 = x.get('privateIpv4', None)

        y = x.get('virtualbox')
        self._disk = y.get('disk', None)
        self._disk_attached = y.get('diskAttached', False)
        self._started = y.get('started', False)

    def get_ssh_name(self):
        assert self._ipv4
        return self._ipv4

    def get_ssh_flags(self):
        copy = self.depl.tempdir + "/id_charon-virtualbox"
        if not os.path.exists(copy):
            shutil.copy(self.depl.expr_path + "/id_charon-virtualbox", copy)
            os.chmod(copy, stat.S_IRUSR | stat.S_IWUSR)
        return ["-o", "StrictHostKeyChecking=no", "-i", copy]

    def get_physical_spec(self, machines):
        return ['    require = [ <charon/virtualbox-image-charon.nix> ];',
                '    nixpkgs.system = pkgs.lib.mkOverride 900 "x86_64-linux";']
    
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
        try:
            lines = subprocess.check_output(
                ["VBoxManage", "showvminfo", "--machinereadable", self._vm_id]).splitlines()
        except subprocess.CalledProcessError:
            raise Exception("unable to get info on VirtualBox VM ‘{0}’".format(self.name))
        vminfo = {}
        for l in lines:
            (k, v) = l.split("=", 1)
            vminfo[k] = v
        return vminfo

    
    def create(self, defn, check):
        assert isinstance(defn, VirtualBoxDefinition)
        
        if not self._vm_id:
            print >> sys.stderr, "creating VirtualBox VM ‘{0}’...".format(self.name)
            
            vm_id = "charon-{0}-{1}".format(self.depl.uuid, self.name)
        
            res = subprocess.call(["VBoxManage", "createvm", "--name", vm_id, "--ostype", "Linux", "--register"])
            if res != 0:
                raise Exception("unable to create VirtualBox VM ‘{0}’".format(self.name))

            self._vm_id = vm_id
            self.write()

        if not self._disk:
            vm_dir = os.environ['HOME'] + "/VirtualBox VMs/" + self._vm_id
            if not os.path.isdir(vm_dir):
                raise Exception("can't find directory of VirtualBox VM ‘{0}’".format(self.name))

            disk = vm_dir + "/disk1.vdi"

            base_image = defn._base_image
            if base_image == "drv":
                try:
                    base_image = subprocess.check_output(
                        ["nix-build", "-I", "charon=" + self.depl.expr_path, "--show-trace",
                         "<charon/eval-machine-info.nix>",
                         "--arg", "networkExprs", "[ " + " ".join(self.depl.nix_exprs) + " ]",
                         "-A", "nodes." + self.name + ".config.deployment.virtualbox.baseImage",
                         "-o", "{0}/vbox-image-{1}".format(self.depl.tempdir, self.name)]).rstrip()
                except subprocess.CalledProcessError:
                    raise Exception("unable to build base image")

            res = subprocess.call(["VBoxManage", "clonehd", base_image, disk])
            if res != 0: raise Exception("unable to copy VirtualBox disk from ‘{0}’ to ‘{1}’".format(base_image, disk))

            self._disk = disk
            self.write()

        if not self._disk_attached:
            res = subprocess.call(
                ["VBoxManage", "storagectl", self._vm_id,
                 "--name", "SATA", "--add", "sata", "--sataportcount", "2",
                 "--bootable", "on", "--hostiocache", "on"])
            if res != 0: raise Exception("unable to create SATA controller on VirtualBox VM ‘{0}’".format(self.name))
            
            res = subprocess.call(
                ["VBoxManage", "storageattach", self._vm_id,
                 "--storagectl", "SATA", "--port", "0", "--device", "0",
                 "--type", "hdd", "--medium", self._disk])
            if res != 0: raise Exception("unable to attach disk to VirtualBox VM ‘{0}’".format(self.name))
            
            self._disk_attached = True
            self.write()

        if check:
            vminfo = self._get_vm_info()
            if vminfo['VMState'] == '"running"':
                self._started = True
            else:
                print >> sys.stderr, "VirtualBox VM ‘{0}’ went down, restarting...".format(self.name)
                self._started = False
                self.write()

        if not self._started:
            res = subprocess.call(
                ["VBoxManage", "modifyvm", self._vm_id,
                 "--memory", "512", "--vram", "10",
                 "--nictype1", "virtio", "--nictype2", "virtio",
                 "--nic2", "hostonly", "--hostonlyadapter2", "vboxnet0",
                 "--nestedpaging", "off"])
            if res != 0: raise Exception("unable to modify VirtualBox VM ‘{0}’".format(self.name))

            res = subprocess.call(["VBoxManage", "startvm", self._vm_id])
            if res != 0: raise Exception("unable to start VirtualBox VM ‘{0}’".format(self.name))

            self._started = True
            self.write()

        if not self._ipv4 or check:
            sys.stderr.write("waiting for IP address of ‘{0}’...".format(self.name))
            while True:
                try:
                    res = subprocess.check_output(
                        ["VBoxManage", "guestproperty", "get", self._vm_id, "/VirtualBox/GuestInfo/Net/1/V4/IP"]).rstrip()
                    if res[0:7] == "Value: ":
                        self._ipv4 = res[7:]
                        sys.stderr.write(" " + self._ipv4 + "\n")
                        break
                except subprocess.CalledProcessError:
                    raise Exception("unable to get IP address of VirtualBox VM ‘{0}’".format(self.name))
                time.sleep(1)
                sys.stderr.write(".")

            charon.known_hosts.remove(self._ipv4)
            
            self.write()

            
    def destroy(self):
        print >> sys.stderr, "destroying VirtualBox VM ‘{0}’...".format(self.name)
        
        subprocess.call(["VBoxManage", "controlvm", self._vm_id, "poweroff"])

        # !!! Stupid asynchronous commands.  Should wait here until
        # the VM is shut down.
        time.sleep(2)

        res = subprocess.call(["VBoxManage", "unregistervm", "--delete", self._vm_id])
        if res != 0: raise Exception("unable to unregister VirtualBox VM ‘{0}’".format(self.name))
