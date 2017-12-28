# -*- coding: utf-8 -*-

from distutils import spawn
import os
import copy
import json
import random
import shutil
import string
import subprocess
import time
from xml.etree import ElementTree

import libvirt

from nixops.backends import MachineDefinition, MachineState
import nixops.known_hosts
import nixops.util

# to prevent libvirt errors from appearing on screen, see
# https://www.redhat.com/archives/libvirt-users/2017-August/msg00011.html

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
        self.domain_type = x.find("attr[@name='domainType']/string").get("value")
        self.kernel = x.find("attr[@name='kernel']/string").get("value")
        self.initrd = x.find("attr[@name='initrd']/string").get("value")
        self.cmdline = x.find("attr[@name='cmdline']/string").get("value")
        self.storage_pool_name = x.find("attr[@name='storagePool']/string").get("value")
        self.uri = x.find("attr[@name='URI']/string").get("value")

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
    storage_volume_name = nixops.util.attr_property("libvirtd.storageVolume", None)
    storage_pool_name = nixops.util.attr_property("libvirtd.storagePool", None)
    vcpu = nixops.util.attr_property("libvirtd.vcpu", None)

    # older deployments may not have a libvirtd.URI attribute in the state file
    # using qemu:///system in such case
    uri = nixops.util.attr_property("libvirtd.URI", "qemu:///system")

    @classmethod
    def get_type(cls):
        return "libvirtd"

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        self._dom = None
        self._pool = None
        self._vol = None

    def connect(self):
        self.logger.log('Connecting to {}...'.format(self.uri))
        self.conn = libvirt.open(self.uri)
        if self.conn is None:
            self.log('Failed to open connection to the hypervisor at {}'.format(self.uri))
            sys.exit(1)

    @property
    def dom(self):
        self.connect()
        if self._dom is None:
            try:
                self._dom = self.conn.lookupByName(self._vm_id())
            except Exception as e:
                self.log("Warning: %s" % e)
        return self._dom

    @property
    def pool(self):
        if self._pool is None:
            self._pool = self.conn.storagePoolLookupByName(self.storage_pool_name)
        return self._pool

    @property
    def vol(self):
        if self._vol is None:
            self._vol = self.pool.storageVolLookupByName(self.storage_volume_name)
        return self._vol

    def get_console_output(self):
        import sys
        return self._logged_exec(["virsh", "-c", self.uri, 'console', self.vm_id.decode()],
                stdin=sys.stdin)

    def get_ssh_private_key_file(self):
        return self._ssh_private_key_file or self.write_ssh_private_key(self.client_private_key)

    def get_ssh_flags(self, *args, **kwargs):
        super_flags = super(LibvirtdState, self).get_ssh_flags(*args, **kwargs)
        return super_flags + ["-o", "StrictHostKeyChecking=accept-new",
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
        self.storage_pool_name = defn.storage_pool_name
        self.uri = defn.uri

        self.connect()

        # required for virConnectGetDomainCapabilities()
        # https://libvirt.org/formatdomaincaps.html
        if self.conn.getLibVersion() < 1002007:
            raise Exception('libvirt 1.2.7 or newer is required at the target host')

        if not self.primary_mac:
            self._generate_primary_mac()

        if not self.client_public_key:
            (self.client_private_key, self.client_public_key) = nixops.util.create_key_pair()

        if self.storage_volume_name is None:
            self._prepare_storage_volume()
            self.storage_volume_name = self.vol.name()

        self.domain_xml = self._make_domain_xml(defn)

        if self.vm_id is None:
            # By using "define" we ensure that the domain is
            # "persistent", as opposed to "transient" (i.e. removed on reboot).
            self._dom = self.conn.defineXML(self.domain_xml)
            if self._dom is None:
                self.log('Failed to register domain XML with the hypervisor')
                return False

            self.vm_id = self._vm_id()

        self.start()
        return True

    def _prepare_storage_volume(self):
        self.logger.log("preparing disk image...")
        newEnv = copy.deepcopy(os.environ)
        newEnv["NIXOPS_LIBVIRTD_PUBKEY"] = self.client_public_key
        base_image = self._logged_exec(
            ["nix-build"] + self.depl._eval_flags(self.depl.nix_exprs) +
            ["--arg", "checkConfigurationOptions", "false",
             "-A", "nodes.{0}.config.deployment.libvirtd.baseImage".format(self.name),
             "-o", "{0}/libvirtd-image-{1}".format(self.depl.tempdir, self.name)],
            capture_stdout=True, env=newEnv).rstrip()

        temp_disk_path = os.path.join(self.depl.tempdir, 'disk.qcow2')
        shutil.copyfile(base_image + "/disk.qcow2", temp_disk_path)
        # Rebase onto empty backing file to prevent breaking the disk image
        # when the backing file gets garbage collected.
        self._logged_exec(["qemu-img", "rebase", "-f", "qcow2", "-b",
                           "", temp_disk_path])

        self.logger.log("uploading disk image...")
        image_info = self._get_image_info(temp_disk_path)
        self._vol = self._create_volume(image_info['virtual-size'], image_info['actual-size'])
        self._upload_volume(temp_disk_path, image_info['actual-size'])

    def _get_image_info(self, filename):
        output = self._logged_exec(["qemu-img", "info", "--output", "json", filename], capture_stdout=True)
        return json.loads(output)

    def _create_volume(self, virtual_size, actual_size):
        xml = '''
        <volume>
          <name>{name}</name>
          <capacity>{virtual_size}</capacity>
          <allocation>{actual_size}</allocation>
          <target>
            <format type="qcow2"/>
          </target>
        </volume>
        '''.format(
            name="{}.qcow2".format(self._vm_id()),
            virtual_size=virtual_size,
            actual_size=actual_size,
        )
        vol = self.pool.createXML(xml)
        self._vol = vol
        return vol

    def _upload_volume(self, filename, actual_size):
        stream = self.conn.newStream()
        self.vol.upload(stream, offset=0, length=actual_size)

        def read_file(stream, nbytes, f):
            return f.read(nbytes)

        with open(filename, 'rb') as f:
            stream.sendAll(read_file, f)
            stream.finish()

    def _get_qemu_executable(self):
        domaincaps_xml = self.conn.getDomainCapabilities(
            emulatorbin=None, arch='x86_64', machine=None, virttype='kvm',
        )
        domaincaps = ElementTree.fromstring(domaincaps_xml)
        return domaincaps.find('./path').text.strip()

    def _make_domain_xml(self, defn):
        qemu = self._get_qemu_executable()

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

        def _make_os(defn):
            return [
                '<os>',
                '    <type arch="x86_64">hvm</type>',
                "    <kernel>%s</kernel>" % defn.kernel,
                "    <initrd>%s</initrd>" % defn.initrd if len(defn.kernel) > 0 else "",
                "    <cmdline>%s</cmdline>"% defn.cmdline if len(defn.kernel) > 0 else "",
                '</os>']


        domain_fmt = "\n".join([
            '<domain type="{5}">',
            '  <name>{0}</name>',
            '  <memory unit="MiB">{1}</memory>',
            '  <vcpu>{4}</vcpu>',
            '\n'.join(_make_os(defn)),
            '  <devices>',
            '    <emulator>{2}</emulator>',
            '    <disk type="file" device="disk">',
            '      <driver name="qemu" type="qcow2"/>',
            '      <source file="{3}"/>',
            '      <target dev="hda"/>',
            '    </disk>',
            '\n'.join([iface(n) for n in defn.networks]),
            '    <graphics type="vnc" port="-1" autoport="yes"/>' if not defn.headless else "",
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
            self.vol.path(),
            defn.vcpu,
            defn.domain_type
        )

    def _parse_ip(self):
        """
        return an ip v4
        """
        # alternative is VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE if qemu agent is available
        ifaces = self.dom.interfaceAddresses(libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE, 0)
        if (ifaces == None):
            self.log("Failed to get domain interfaces")
            return

        for (name, val) in ifaces.iteritems():
            if val['addrs']:
                for ipaddr in val['addrs']:
                    return ipaddr['addr']

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
            return self.dom.isActive()
        except libvirt.libvirtError:
            self.log("Domain %s is not running" % self.vm_id)
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
        self.private_ipv4 = self._parse_ip()
        return self.private_ipv4

    def stop(self):
        assert self.vm_id
        if self._is_running():
            self.log_start("shutting down... ")
            if self.dom.destroy() != 0:
                self.log("Failed destroying machine")
        else:
            self.log("not running")
        self.state = self.STOPPED

    def destroy(self, wipe=False):
        self.log_start("destroying... ")

        if self.vm_id is not None:
            self.stop()
            if self.dom.undefine() != 0:
                self.log("Failed undefining domain")
                return False

        if (self.disk_path and os.path.exists(self.disk_path)):
            # the deployment was created by an older NixOps version that did
            # not use the libvirtd API for uploading disk images
            os.unlink(self.disk_path)

        if self.storage_volume_name is not None:
            self.vol.delete()

        return True
