# -*- coding: utf-8 -*-

from distutils import spawn
import os
import copy
import random
import shutil
import string
import subprocess
import time
import libvirt

from nixops.backends import MachineDefinition, MachineState
import nixops.known_hosts
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
        assert self.image_dir is not None
        self.domain_type = x.find("attr[@name='domainType']/string").get("value")

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
    vcpu = nixops.util.attr_property("libvirtd.vcpu", None)

    @classmethod
    def get_type(cls):
        return "libvirtd"

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)

        self.conn = libvirt.open(None)
        if self.conn == None:
            self.log('Failed to open connection to the hypervisor')
            sys.exit(1)
        self.dom = self.conn.lookupByName(self.vm_id)

    def get_ssh_private_key_file(self):
        return self._ssh_private_key_file or self.write_ssh_private_key(self.client_private_key)

    def get_ssh_flags(self, *args, **kwargs):
        super_flags = super(LibvirtdState, self).get_ssh_flags(*args, **kwargs)
        return super_flags + ["-o", "StrictHostKeyChecking=no",
                              "-i", self.get_ssh_private_key_file()]

    def get_physical_spec(self):
        return {('users', 'extraUsers', 'root', 'openssh', 'authorizedKeys', 'keys'): [self.client_public_key]}

    def address_to(self, m):
        if isinstance(m, LibvirtdState):
            return m.private_ipv4
        return MachineState.address_to(self, m)

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
            shutil.copyfile(base_image + "/disk.qcow2", self.disk_path)
            # Rebase onto empty backing file to prevent breaking the disk image
            # when the backing file gets garbage collected.
            self._logged_exec(["qemu-img", "rebase", "-f", "qcow2", "-b",
                               "", self.disk_path])
            os.chmod(self.disk_path, 0660)
            self.vm_id = self._vm_id()
            dom_file = self.depl.tempdir + "/{0}-domain.xml".format(self.name)
            # nixops.util.write_file(dom_file, self.domain_xml)
            # By using "virsh define" we ensure that the domain is
            # "persistent", as opposed to "transient" (removed on reboot).

            # TODO use define
            self.dom = self.conn.defineXML(self.domain_xml)

            # self._logged_exec(["virsh", "-c", "qemu:///system", "define", dom_file])
        self.start()
        return True

    def _disk_path(self, defn):
        return "{0}/{1}.img".format(defn.image_dir, self._vm_id())

    def _make_domain_xml(self, defn):
        qemu_executable = "qemu-system-x86_64"
        qemu = spawn.find_executable(qemu_executable)
        assert qemu is not None, "{} executable not found. Please install QEMU first.".format(qemu_executable)

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
            '<domain type="{5}">',
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
            defn.vcpu,
            defn.domain_type
        )

    def _parse_ip(self):
        cmd = [
            "virsh",
            "-c",
            "qemu:///system",
            "net-dhcp-leases",
            "--network",
            self.primary_net,
        ]
        lines = subprocess.check_output(cmd)
        try:
            i = lines.split().index(self.primary_mac)
        except ValueError:
            pass
        else:
            ip_with_subnet = lines.split()[i + 2]
            return ip_with_subnet.split('/')[0]

    def _wait_for_ip(self, prev_time):
        self.log_start("waiting for IP address to appear in DHCP leases...")
        while True:
            ip = self._parse_ip()
            if ip:
                self.private_ipv4 = ip
                break
            time.sleep(1)
            self.log_continue(".")
        self.log_end(" " + self.private_ipv4)

    def _is_running(self):
        try:
            return self.dom.info()[1] == libvirt.VIR_DOMAIN_RUNNING
        except libvirt.libvirtError:
            self.log( "Domain %s is not runing" % self.vm_id)
        return False

    def start(self):
        assert self.vm_id
        assert self.domain_xml
        assert self.primary_net
        if self._is_running():
            self.log("connecting...")
            self.private_ipv4 = self._parse_ip()
        else:
            self.log("starting...")
            self.dom.create()
            self._wait_for_ip(0)

    def get_ssh_name(self):
        assert self.private_ipv4
        return self.private_ipv4

    def stop(self):
        assert self.vm_id
        if self._is_running():
            self.log_start("shutting down... ")
            self.dom.destroy()
        else:
            self.log("not running")
        self.state = self.STOPPED

    def destroy(self, wipe=False):
        if not self.vm_id:
            return True
        self.log_start("destroying... ")
        self.stop()
        self.dom.undefine()
        if (self.disk_path and os.path.exists(self.disk_path)):
            os.unlink(self.disk_path)
        return True
