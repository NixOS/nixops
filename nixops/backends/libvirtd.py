# -*- coding: utf-8 -*-

from distutils import spawn
import os
import random
import string
import subprocess
import time

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
        self.memory_size = x.find("attr[@name='memorySize']/int").get("value")
        self.extra_devices = x.find("attr[@name='extraDevicesXML']/string").get("value")
        self.image_dir = x.find("attr[@name='imageDir']/string").get("value")
        assert self.image_dir is not None

        self.networks = [
            k.get("value")
            for k in x.findall("attr[@name='networks']/list/string")]
        assert len(self.networks) > 0


class LibvirtdState(MachineState):
    private_ipv4 = nixops.util.attr_property("privateIpv4", None)
    client_public_key = nixops.util.attr_property("libvirtd.clientPublicKey", None)
    client_private_key = nixops.util.attr_property("libvirtd.clientPrivateKey", None)
    primary_net = nixops.util.attr_property("libvirtd.primaryNet", None)
    primary_mac = nixops.util.attr_property("libvirtd.primaryMAC", None)
    domain_xml = nixops.util.attr_property("libvirtd.domainXML", None)
    disk_path = nixops.util.attr_property("libvirtd.diskPath", None)

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

    def _generate_primary_mac(self):
        mac = [0x52, 0x54, 0x00,
               random.randint(0x00, 0x7f),
               random.randint(0x00, 0xff),
               random.randint(0x00, 0xff)]
        self.primary_mac = ':'.join(map(lambda x: "%02x" % x, mac))

    def create(self, defn, check, allow_reboot, allow_recreate):
        assert isinstance(defn, LibvirtdDefinition)
        self.set_common_state(defn)
        self.primary_net = defn.networks[0]
        if not self.primary_mac:
            self._generate_primary_mac()
        self.domain_xml = self._make_domain_xml(defn)

        if not self.client_public_key:
            (self.client_private_key, self.client_public_key) = nixops.util.create_key_pair()

        if self.vm_id is None:
            os.putenv("NIXOPS_LIBVIRTD_PUBKEY", self.client_public_key)
            base_image = self._logged_exec(
                ["nix-build"] + self.depl._eval_flags(self.depl.nix_exprs) +
                ["--arg", "checkConfigurationOptions", "false",
                 "-A", "nodes.{0}.config.deployment.libvirtd.baseImage".format(self.name),
                 "-o", "{0}/libvirtd-image-{1}".format(self.depl.tempdir, self.name)],
                capture_stdout=True).rstrip()

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

    def has_really_fast_connection(self):
        return True

    def _disk_path(self, defn):
        return "{0}/{1}.img".format(defn.image_dir, self._vm_id())

    def _make_domain_xml(self, defn):
        def maybe_mac(n):
            if n == self.primary_net:
                return '<mac address="' + self.primary_mac + '" />'
            else:
                return ""

        def iface(n):
            return "\n".join([
                '    <interface type="network">',
                maybe_mac(n),
                '      <source network="{0}"/>',
                '    </interface>',
            ]).format(n)

        domain_fmt = "\n".join([
            '<domain type="kvm">',
            '  <name>{0}</name>',
            '  <memory unit="MiB">{1}</memory>',
            '  <vcpu>1</vcpu>',
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
            '    <graphics type="sdl" display=":0.0"/>',
            '    <input type="keyboard" bus="usb"/>',
            '    <input type="mouse" bus="usb"/>',
            defn.extra_devices,
            '  </devices>',
            '</domain>',
        ])

        qemu_kvm = spawn.find_executable("qemu-kvm")
        assert qemu_kvm is not None, "qemu-kvm executable not found"

        return domain_fmt.format(
            self._vm_id(),
            defn.memory_size,
            qemu_kvm,
            self._disk_path(defn),
        )

    def _parse_lease(self):
        for line in open("/var/lib/libvirt/dnsmasq/{0}.leases".format(self.primary_net)):
            flds = line.split()
            if (flds[1] == self.primary_mac):
                return (flds[0], flds[2])
        return (0, None)

    def _wait_for_ip(self, prev_time):
        self.log_start("waiting for IP address...")
        while True:
            (l_time, l_ip) = self._parse_lease()
            if (l_time > prev_time):
                self.private_ipv4 = l_ip
                break
            time.sleep(1)
            self.log_continue(".")
        self.log_end(" " + self.private_ipv4)

    def _is_running(self):
        ls = subprocess.check_output(["virsh", "-c", "qemu:///system", "list"])
        return (string.find(ls, self.vm_id) != -1)

    def start(self):
        assert self.vm_id
        assert self.domain_xml
        assert self.primary_net
        (l_time, l_ip) = self._parse_lease()
        if self._is_running():
            self.private_ipv4 = l_ip
        else:
            dom_file = self.depl.tempdir + "/{0}-domain.xml".format(self.name)
            nixops.util.write_file(dom_file, self.domain_xml)
            self._logged_exec(["virsh", "-c", "qemu:///system", "create", dom_file])
            self._wait_for_ip(l_time)

    def get_ssh_name(self):
        assert self.private_ipv4
        return self.private_ipv4

    def stop(self):
        assert self.vm_id
        if self._is_running():
            self._logged_exec(["virsh", "-c", "qemu:///system", "destroy", self.vm_id])

    def destroy(self, wipe=False):
        if not self.vm_id:
            return True
        self.stop()
        if (self.disk_path and os.path.exists(self.disk_path)):
            os.unlink(self.disk_path)
        return True
