# -*- coding: utf-8 -*-

from distutils import spawn
import os
import copy
import random
import string
import subprocess
import time
import re
from xml.etree import ElementTree

from nixops.backends import MachineDefinition, MachineState
import nixops.util


class LibvirtdDefinition(MachineDefinition):
    """Definition of a trivial machine."""
    @classmethod
    def get_type(cls):
        return "libvirtd"

    def __init__(self, xml, config):
        MachineDefinition.__init__(self, xml, config)

        x = xml.find("attrs/attr[@name='libvirtd']/attrs")
        assert x is not None
        self.vcpu = x.find("attr[@name='vcpu']/int").get("value")
        self.memory_size = x.find("attr[@name='memorySize']/int").get("value")
        self.extra_devices = x.find("attr[@name='extraDevicesXML']/string").get("value")
        self.extra_domain = x.find("attr[@name='extraDomainXML']/string").get("value")
        self.headless = x.find("attr[@name='headless']/bool").get("value") == 'true'
        self.image_dir = x.find("attr[@name='imageDir']/string").get("value")
        self.private_ipv4_setting = x.find("attr[@name='privateIPv4']/string").get("value")
        assert self.image_dir is not None

        self.networks = [
            k.get("value")
            for k in x.findall("attr[@name='networks']/list/string")]
        assert len(self.networks) > 0


class LibvirtdState(MachineState):
    private_ipv4 = nixops.util.attr_property("privateIpv4", None)
    private_ipv4_setting = nixops.util.attr_property("libvirtd.privateIpv4Setting", "dhcp") # Default for retro-compatibility
    client_public_key = nixops.util.attr_property("libvirtd.clientPublicKey", None)
    client_private_key = nixops.util.attr_property("libvirtd.clientPrivateKey", None)
    domain_xml = nixops.util.attr_property("libvirtd.domainXML", None)
    disk_path = nixops.util.attr_property("libvirtd.diskPath", None)
    vcpu = nixops.util.attr_property("libvirtd.vcpu", None)

    @classmethod
    def get_type(cls):
        return "libvirtd"

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)

    def get_ssh_private_key_file(self):
        return self._ssh_private_key_file or self.write_ssh_private_key(self.client_private_key)

    def get_ssh_flags(self, *args, **kwargs):
        super_flags = super(LibvirtdState, self).get_ssh_flags(*args, **kwargs)
        return super_flags + ["-o", "StrictHostKeyChecking=no",
                              "-i", self.get_ssh_private_key_file()]

    def _vm_id(self):
        return "nixops-{0}-{1}".format(self.depl.uuid, self.name)

    def create(self, defn, check, allow_reboot, allow_recreate):
        assert isinstance(defn, LibvirtdDefinition)
        self.set_common_state(defn)
        self.private_ipv4_setting = defn.private_ipv4_setting
        self.domain_xml = self._make_domain_xml(defn)

        if not self.client_public_key:
            (self.client_private_key, self.client_public_key) = nixops.util.create_key_pair()

        if self.vm_id is None:
            newEnv = copy.deepcopy(os.environ)
            newEnv["NIXOPS_LIBVIRTD_PUBKEY"] = self.client_public_key
            base_image = self._logged_exec(
                ["nix-build"] + self.depl._eval_flags(self.depl.nix_exprs) +
                ["--arg", "checkConfigurationOptions", "false",
                 "-A", "nodes.{0}.config.deployment.libvirtd.baseImage".format(self.name),
                 "-o", "{0}/libvirtd-image-{1}".format(self.depl.tempdir, self.name)],
                capture_stdout=True, env=newEnv).rstrip()

            if not os.access(defn.image_dir, os.W_OK):
                raise Exception('{} is not writable by this user or it does not exist'.format(defn.image_dir))

            self.disk_path = self._disk_path(defn)
            self._logged_exec(["qemu-img", "create", "-f", "qcow2", "-b",
                               base_image + "/disk.qcow2", self.disk_path])
            # TODO: use libvirtd.extraConfig to make the image accessible for your user
            os.chmod(self.disk_path, 0666)
            self.vm_id = self._vm_id()
        self.start()
        return True

    def _disk_path(self, defn):
        return "{0}/{1}.img".format(defn.image_dir, self._vm_id())

    def _make_domain_xml(self, defn):
        qemu_executable = "qemu-system-x86_64"
        qemu = spawn.find_executable(qemu_executable)
        assert qemu is not None, "{} executable not found. Please install QEMU first.".format(qemu_executable)

        def iface(n):
            return "\n".join([
                '    <interface type="network">',
                '      <source network="{0}"/>',
                '    </interface>',
            ]).format(n)

        domain_fmt = "\n".join([
            '<domain type="kvm">',
            '  <name>{0}</name>',
            '  <memory unit="MiB">{1}</memory>',
            '  <vcpu>{4}</vcpu>',
            '  <os>',
            '    <type arch="x86_64">hvm</type>',
            '  </os>',
            '  <devices>',
            '    <emulator>{2}</emulator>',
            '    <disk type="file" device="disk">',
            '      <driver name="qemu" type="qcow2"/>',
            '      <source file="{3}"/>',
            '      <target dev="hda"/>',
            '    </disk>',
            '\n'.join([iface(n) for n in defn.networks]),
            '    <graphics type="sdl" display=":0.0"/>' if not defn.headless else "",
            '    <input type="keyboard" bus="usb"/>',
            '    <input type="mouse" bus="usb"/>',
            defn.extra_devices,
            '  </devices>',
            defn.extra_domain,
            '</domain>',
        ])

        return domain_fmt.format(
            self._vm_id(),
            defn.memory_size,
            qemu,
            self._disk_path(defn),
            defn.vcpu
        )

    def _fetch_ip(self):
        if re.match("^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", self.private_ipv4_setting):
            return self.private_ipv4_setting

        elif self.private_ipv4_setting == "arp":
            # Inspired from https://rwmj.wordpress.com/2010/10/26/tip-find-the-ip-address-of-a-virtual-machine/
            xml = subprocess.check_output(["virsh", "-c", "qemu:///system", "dumpxml", self.vm_id])
            tree = ElementTree.fromstring(xml)
            interfaces = tree.findall("devices/interface[@type='network']")
            nets = [(x.find("source").get("network"), x.find("mac").get("address")) for x in interfaces]
            if len(nets) == 0:
                raise Exception('VM has no networks configured; aborting')
            self.log("Found MAC addresses (and networks) " + repr(nets))

            self.log_start("Waiting for IP address to appear in the ARP table...")
            while True:
                lines = subprocess.check_output(["arp", "-an"]).split("\n")
                for line in lines:
                    r = re.match('[^()]+ \(([0-9.]+)\) at ([0-9a-f:]+) ', line)
                    if not r: continue
                    for net in nets:
                        if r.group(2) == net[1]:
                           ip = r.group(1)
                           self.log_end(" " + ip)
                           self.log("update dhcp leases to assign assigned ip address to hostname")
                           self._logged_exec(
                               ["virsh", "-c", "qemu:///system",
                                "net-update", net[0], "add",
                                "ip-dhcp-host",
                                "<host mac='{0}' name='{1}' ip='{2}' />".format(
                                  net[1], self.name, ip),
                                "--live"
                                ]),
                           return ip
                self.log_continue(".")
                time.sleep(1)

        elif self.private_ipv4_setting == "dhcp":
            xml = subprocess.check_output(["virsh", "-c", "qemu:///system", "dumpxml", self.vm_id])
            tree = ElementTree.fromstring(xml)
            interfaces = tree.findall("devices/interface[@type='network']")
            nets = [(x.find("source").get("network"), x.find("mac").get("address")) for x in interfaces]
            if len(nets) == 0:
                raise Exception('VM has no networks configured; aborting')
            self.log("Found networks/MAC pairs " + repr(nets))

            self.log_start("Waiting for IP address to appear in DHCP leases...")
            while True:
                for net, mac in nets:
                    # TODO: parse command output with a proper regexp, and/or use "net-dhcp-leases --network <network> [--mac <mac>]"
                    cmd = [ "virsh", "-c", "qemu:///system", "net-dhcp-leases", "--network", net ]
                    lines = subprocess.check_output(cmd).split()
                    try:
                        i = lines.index(mac)
                    except ValueError:
                        continue
                    else:
                        ip_with_subnet = lines[i + 2]
                        ip = ip_with_subnet.split('/')[0]
                        self.log("update dhcp leases to assign assigned ip address to hostname")
                        self._logged_exec(
                            ["virsh", "-c", "qemu:///system",
                             "net-update", net, "add",
                             "ip-dhcp-host",
                             "<host mac='{0}' name='{1}' ip='{2}' />".format(
                                 mac, self.name, ip),
                             "--live"
                             ])
                        self.log_end(" " + ip)
                        return ip

                self.log_continue(".")
                time.sleep(1)

        else:
            raise Exception('"{}" is not a valid value for deployment.libvirtd.privateIPv4'.format(self.private_ipv4_setting))

    def _is_running(self):
        ls = subprocess.check_output(["virsh", "-c", "qemu:///system", "list"])
        return (string.find(ls, self.vm_id) != -1)

    def _is_network_running(self,net):
        ls = subprocess.check_output(["virsh", "-c", "qemu:///system", "net-list"])
        return (string.find(ls, net) != -1)

    def start(self):
        assert self.vm_id
        assert self.domain_xml
        if self._is_running():
            self.log("connecting...")
        else:
            self.log("starting...")
            dom_file = self.depl.tempdir + "/{0}-domain.xml".format(self.name)
            nixops.util.write_file(dom_file, self.domain_xml)
            self._logged_exec(["virsh", "-c", "qemu:///system", "create", dom_file])
        self.private_ipv4 = self._fetch_ip()

    def get_ssh_name(self):
        assert self.private_ipv4
        return self.private_ipv4
    def stop(self):
        assert self.vm_id
        if self._is_running():
            self.log_start("shutting down... ")
            self._logged_exec(["virsh", "-c", "qemu:///system", "destroy", self.vm_id])
        else:
            self.log("not running")

    def _restartLibvirtNetworks(self, net):
        if (self._is_network_running(net)):
          self.log("restarting libvirt network(s) to cancel static ip assignments")
          self.log(net)
          self._logged_exec(["virsh", "-c", "qemu:///system", "net-destroy", net])
          self._logged_exec(["virsh", "-c", "qemu:///system", "net-start", net])

    def _globalPreDestroyHook(self):
        self.log("running globalPreDestroyHook")
        xml = subprocess.check_output(["virsh", "-c", "qemu:///system", "dumpxml", self.vm_id])
        tree = ElementTree.fromstring(xml)
        interfaces = tree.findall("devices/interface[@type='network']")
        nets = [x.find("source").get("network") for x in interfaces]
        map(self._restartLibvirtNetworks, nets)

    def destroy(self, wipe=False):
        if not self.vm_id:
            return True
        self.log_start("destroying... ")
        self.stop()
        if (self.disk_path and os.path.exists(self.disk_path)):
            os.unlink(self.disk_path)
        return True
