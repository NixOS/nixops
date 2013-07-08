# -*- coding: utf-8 -*-
import os
import sys
import subprocess

import nixops.util
from nixops.hetzner_utils import Robot
from nixops.backends import MachineDefinition, MachineState


class HetznerDefinition(MachineDefinition):
    """
    Definition of a Hetzner machine.
    """

    @classmethod
    def get_type(cls):
        return "hetzner"

    def __init__(self, xml):
        MachineDefinition.__init__(self, xml)
        x = xml.find("attrs/attr[@name='hetzner']/attrs")
        assert x is not None
        for var, name, valtype in [("main_ipv4", "mainIPv4", "string"),
                                   ("robot_user", "robotUser", "string"),
                                   ("robot_pass", "robotPass", "string"),
                                   ("partitions", "partitions", "string")]:
            attr = x.find("attr[@name='" + name + "']/" + valtype)
            setattr(self, var, attr.get("value"))


class HetznerState(MachineState):
    """
    State of a Hetzner machine.
    """

    @classmethod
    def get_type(cls):
        return "hetzner"

    state = nixops.util.attr_property("state", MachineState.UNKNOWN, int)

    main_ipv4 = nixops.util.attr_property("hetzner.mainIPv4", None)
    robot_user = nixops.util.attr_property("hetzner.robotUser", None)
    robot_pass = nixops.util.attr_property("hetzner.robotPass", None)
    partitions = nixops.util.attr_property("hetzner.partitions", None)

    rescue_passwd = nixops.util.attr_property("rescuePasswd", None)
    partitioner = nixops.util.attr_property("rescuePartitioner", None)
    fs_info = nixops.util.attr_property("fsInfo", None)
    net_info = nixops.util.attr_property("networkInfo", None)

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        self._robot = None

    @property
    def resource_id(self):
        return self.vm_id

    def connect(self):
        """
        Connect to the Hetzner robot.
        """
        if self._robot is not None:
            return True
        elif self.robot_user is None or self.robot_pass is None:
            return False
        self._robot = Robot(self.robot_user, self.robot_pass)
        return True

    def _wait_for_rescue(self, ip):
        self.log_start("waiting for rescue system...")
        nixops.util.wait_for_tcp_port(ip, 22, open=False,
                                      callback=lambda: self.log_continue("."))
        self.log_continue("[down]")
        nixops.util.wait_for_tcp_port(ip, 22,
                                      callback=lambda: self.log_continue("."))
        self.log_end("[up]")
        self.state = self.RESCUE

    def _boot_into_rescue(self):
        if self.state == self.RESCUE:
            return

        self.log("rebooting machine ‘{0}’ ({1}) into rescue system"
                 .format(self.name, self.main_ipv4))
        server = self._get_server_by_ip(self.main_ipv4)
        server.rescue.activate()
        rescue_passwd = server.rescue.password
        server.reboot('hard')
        self._wait_for_rescue(self.main_ipv4)
        self.rescue_passwd = rescue_passwd
        self.has_partitioner = None
        self.state = self.RESCUE

    def _build_locally(self, path):
        return subprocess.check_output([
            "nix-build", "<nixpkgs>", "--no-out-link", "-A", path
        ]).rstrip()

    def _copy_shallow_closure(self, path, basepath="/"):
        paths = subprocess.check_output(['nix-store', '-qR', path])
        local_tar = subprocess.Popen(['tar', 'cJ'] + paths.splitlines(),
                                     stdout=subprocess.PIPE)
        self.run_command("tar xJ -C {0}".format(basepath),
                         stdin=local_tar.stdout)
        local_tar.wait()

    def _install_partitioner(self):
        self.log_start("building partitioner...")
        nixpart = self._build_locally("pythonPackages.nixpartHetzner")
        self.log_end("done ({0})".format(nixpart))

        if self.partitioner is not None and self.partitioner == nixpart:
            return nixpart

        self.log_start("copying partitioner to rescue system...")
        self._copy_shallow_closure(nixpart)
        self.log_end("done.")

        self.partitioner = nixpart
        return nixpart

    def _install_nix_mnt(self):
        self.log_start("building Nix...")
        nix = self._build_locally("nix")
        self.log_end("done ({0})".format(nix))

        self.log_start("copying Nix to /mnt in rescue system...")
        self._copy_shallow_closure(nix, "/mnt")
        self.log_end("done.")

        self.log("creating chroot wrappers in /usr/bin:")
        self.run_command('; '.join([
            'for i in /mnt{0}/bin/*'.format(nix),
            'do storepath="${i#/mnt}"',
            '   echo -n "Creating $target from $i..." >&2',
            '   target="/usr/bin/$(basename "$i")"',
            '   echo "#!/bin/sh" > "$target"',
            r'   echo "chroot /mnt \"$storepath\" \$@" >> "$target"',
            '   chmod +x "$target"',
            '   echo " done." >&2',
            'done',
        ]))

        self.log_start("creating chroot wrapper for activation script...")
        activator = "/nix/var/nix/profiles/system/bin/switch-to-configuration"
        cmd = ' && '.join(['mkdir -p "{0}"',
                           'echo "#!/bin/sh" > "{1}"',
                           r'echo "chroot /mnt \"{1}\" \$@" >> "{1}"',
                           'chmod +x "{1}"'])

        self.run_command(cmd.format(os.path.dirname(activator), activator))
        self.log_end("done.")

    def _install_bin_sh(self):
        self.log_start("building bash...")
        bash = self._build_locally("bash")
        self.log_end("done ({0})".format(bash))

        self.log_start("copying bash to /mnt in rescue system...")
        self._copy_shallow_closure(bash, "/mnt")
        self.log_end("done.")

        msg = "creating symlink from /mnt/bin/sh to {0}..."
        self.log_start(msg.format(bash))
        self.run_command('ln -sf "{0}/bin/bash" /mnt/bin/sh'.format(bash))
        self.log_end("done.")

    def has_really_fast_connection(self):
        # XXX: Remove me after it's possible to use substitutes.
        return True

    def _install_base_system(self):
        if self.state != self.RESCUE:
            return

        nixpart = self._install_partitioner()

        self.log_start("partitioning disks...")
        nixpart_bin = os.path.join(nixpart, "bin/nixpart")
        out = self.run_command("{0} -".format(nixpart_bin),
                               capture_stdout=True,
                               stdin_string=self.partitions)
        self.fs_info = '\n'.join(out.splitlines()[1:-1])
        self.log_end("done.")

        self.log_start("creating missing directories...")
        cmds = ["mkdir -m 1777 -p /mnt/tmp /mnt/nix/store"]
        mntdirs = ["var", "dev", "proc", "sys", "etc", "bin",
                   "nix/var/nix/gcroots", "nix/var/nix/temproots",
                   "nix/var/nix/manifests", "nix/var/nix/userpool",
                   "nix/var/nix/profiles", "nix/var/nix/db",
                   "nix/var/log/nix/drvs"]
        to_create = ' '.join(map(lambda d: os.path.join("/mnt", d), mntdirs))
        cmds.append("mkdir -m 0755 -p {0}".format(to_create))
        self.run_command(' && '.join(cmds))
        self.log_end("done.")

        self.log_start("bind-mounting files in /etc...")
        for etcfile in ("resolv.conf", "passwd", "group"):
            self.log_continue("{0}...".format(etcfile))
            cmd = ("if ! test -e /mnt/etc/{0}; then"
                   " touch /mnt/etc/{0} && mount --bind /etc/{0} /mnt/etc/{0};"
                   " fi").format(etcfile)
            self.run_command(cmd)
        self.log_end("done.")

        self.log_start("bind-mounting other filesystems...")
        for mountpoint in ("/proc", "/dev", "/dev/shm", "/sys"):
            self.log_continue("{0}...".format(mountpoint))
            cmd = "mount --bind {0} /mnt{0}".format(mountpoint)
            self.run_command(cmd)
        self.log_end("done.")

        self.run_command("touch /mnt/etc/NIXOS")
        self._install_bin_sh()
        self._install_nix_mnt()
        self._gen_network_spec()

    def _get_ethernet_interfaces(self):
        # We don't use \(\) here to ensure this works even without GNU sed.
        cmd = "ip addr show | sed -n -e 's/^[0-9]*: *//p' | cut -d: -f1"
        return self.run_command(cmd, capture_stdout=True).splitlines()

    def _get_udev_rule_for(self, interface):
        cmd = "ip addr show \"{0}\" | sed -n -e 's|^.*link/ether  *||p'"
        cmd += " | cut -d' ' -f1"
        mac_addr = self.run_command(cmd.format(interface),
                                    capture_stdout=True).strip()

        rule = 'ACTION=="add", SUBSYSTEM=="net", ATTR{{address}}=="{0}", '
        rule += 'NAME="{1}"'
        return rule.format(mac_addr, interface)

    def _get_ipv4_addr_and_prefix_for(self, interface):
        cmd = "ip addr show \"{0}\" | sed -n -e 's/^.*inet  *//p'"
        cmd += " | cut -d' ' -f1"
        ipv4_addr_prefix = self.run_command(cmd.format(interface),
                                            capture_stdout=True).strip()
        return ipv4_addr_prefix.split('/', 1)

    def _get_default_gw(self):
        cmd = "ip route list | sed -n -e 's/^default  *via  *//p'"
        cmd += " | cut -d' ' -f1"
        return self.run_command(cmd, capture_stdout=True).strip()

    def _get_nameservers(self):
        cmd = "cat /etc/resolv.conf | sed -n -e 's/^nameserver  *//p'"
        return self.run_command(cmd, capture_stdout=True).splitlines()

    def _indent(self, lines, level=1):
        """
        Indent list of lines by the specified level (one level = two spaces).
        """
        return map(lambda line: "  " + line, lines)

    def _gen_network_spec(self):
        udev_rules = []
        iface_attrs = []

        # interface-specific networking options
        for iface in self._get_ethernet_interfaces():
            if iface == "lo":
                continue

            udev_rules.append(self._get_udev_rule_for(iface))
            ipv4, prefix = self._get_ipv4_addr_and_prefix_for(iface)
            quotedipv4 = '"{0}"'.format(ipv4)
            baseattr = 'networking.interfaces.{0}.{1} = {2};'
            iface_attrs.append(baseattr.format(iface, "ipAddress", quotedipv4))
            iface_attrs.append(baseattr.format(iface, "prefixLength", prefix))

        # global networking options
        defgw = self._get_default_gw()
        nameservers = self._get_nameservers()

        udev_attrs = ["services.udev.extraRules = ''"]
        udev_attrs += self._indent(udev_rules)
        udev_attrs += ["'';"]

        attrs = iface_attrs + udev_attrs + [
            'networking.defaultGateway = "{0}";'.format(defgw),
            'networking.nameservers = [ {0} ];'.format(
                ' '.join(map(lambda ns: '"{0}"'.format(ns), nameservers))
            ),
        ]
        self.net_info = "\n".join(self._indent(attrs))

    def get_physical_spec(self):
        return self._indent(
            self.net_info.splitlines() + self.fs_info.splitlines()
        )

    def create(self, defn, check, allow_reboot, allow_recreate):
        assert isinstance(defn, HetznerDefinition)

        if self.state not in (self.RESCUE, self.UP) or check:
            self.check()

        self.set_common_state(defn)
        self.robot_user = defn.robot_user
        self.robot_pass = defn.robot_pass
        self.main_ipv4 = defn.main_ipv4
        self.partitions = defn.partitions

        if not self.vm_id:
            self.log("installing machine...")
            self._boot_into_rescue()
            self._install_base_system()
            self.vm_id = "nixops-{0}-{1}".format(self.depl.uuid, self.name)

    def start(self):
        server = self._get_server_by_ip(defn.main_ipv4)
        server.reboot()

    def stop(self):
        """
        "Stops" the server by putting it into the rescue system.
        """
        pass

    def get_ssh_name(self):
        assert self.main_ipv4
        return self.main_ipv4

    def get_ssh_password(self):
        if self.state == self.RESCUE:
            return self.rescue_passwd
        else:
            return None

    def _get_server_by_ip(self, ip):
        """
        Return the server robot instance by its main IPv4 address.
        """
        if self.connect():
            return self._robot.servers.get(ip)
        else:
            return None

    def _check(self, res):
        if not self.vm_id:
            res.exists = False
            return

        avg = self.get_load_avg()
        if avg is None:
            if self.state in (self.UP, self.RESCUE):
                self.state = self.UNREACHABLE
            res.is_reachable = False
        elif self.run_command("test -f /etc/NIXOS", check=False) != 0:
            self.state = self.RESCUE
            self.ssh_pinged = True
            self._ssh_pinged_this_time = True
            res.is_reachable = True
        else:
            MachineState._check(self, res)

    def destroy(self):
        return True
