# -*- coding: utf-8 -*-
"""
A backend for www.digitalocean.com (short as "DO").

This backend uses nixos-infect (which uses nixos LUSTRATE) to infect a
Ubuntu digitial ocean instance. The setup requires two reboots, one for
the infect itself, another after we pushed the nixos image.

I hit a few subtle problems along the way:
* DO doesn't do dhcp so we have to hard-code the network configuration
* Ubuntu still uses eth0, 1 etc, not ens3 etc so we have a network
  link name change after the reboot.
* I had to modify nixos-infect to reflect the network link name changes,
  and to not reboot to avoid ssh-interruption and therefore errors.

Still to do:
* Floating IPs
* Network attached storage
"""
import os
import os.path
import time
import nixops.resources
from nixops.backends import MachineDefinition, MachineState
from nixops.nix_expr import Function, RawValue
import nixops.util
import nixops.known_hosts
import socket
import digitalocean

infect_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'nixos-infect'))


class DigitalOceanDefinition(MachineDefinition):
    @classmethod
    def get_type(cls):
        return "digitalOcean"

    def __init__(self, xml, config):
        MachineDefinition.__init__(self, xml, config)
        self.auth_token = config["digitalOcean"]["authToken"]
        self.region = config["digitalOcean"]["region"]
        self.size = config["digitalOcean"]["size"]
        self.enable_ipv6 = config["digitalOcean"]["enableIpv6"]

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region)


class DigitalOceanState(MachineState):
    @classmethod
    def get_type(cls):
        return "digitalOcean"

    state = nixops.util.attr_property("state", MachineState.MISSING, int)  # override
    public_ipv4 = nixops.util.attr_property("publicIpv4", None)
    default_gateway = nixops.util.attr_property("defaultGateway", None)
    netmask = nixops.util.attr_property("netmask", None)
    enable_ipv6 = nixops.util.attr_property("digitalOcean.enableIpv6", False, bool)
    public_ipv6 = nixops.util.attr_property("publicIpv6", {}, 'json')
    default_gateway6 = nixops.util.attr_property("defaultGateway6", None)
    region = nixops.util.attr_property("digitalOcean.region", None)
    size = nixops.util.attr_property("digitalOcean.size", None)
    auth_token = nixops.util.attr_property("digitalOcean.authToken", None)
    droplet_id = nixops.util.attr_property("digitalOcean.dropletId", None)
    key_pair = nixops.util.attr_property("digitalOcean.keyPair", None)

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        self.name = name

    def get_ssh_name(self):
        return self.public_ipv4

    def get_ssh_flags(self, *args, **kwargs):
        super_flags = super(DigitalOceanState, self).get_ssh_flags(*args, **kwargs)
        return super_flags + [
            '-o', 'UserKnownHostsFile=/dev/null',
            '-o', 'StrictHostKeyChecking=accept-new',
            '-i', self.get_ssh_private_key_file(),
        ]

    def get_physical_spec(self):
        def prefix_len(netmask):
            return bin(int(socket.inet_aton(netmask).encode('hex'), 16)).count('1')
        networking = {
            'defaultGateway': self.default_gateway,
            'nameservers': ['8.8.8.8'], # default provided by DO
            ('interfaces', 'ens3', 'ip4'): [{"address": self.public_ipv4, 'prefixLength': prefix_len(self.netmask)}],
        }
        if self.public_ipv6:
            networking[('interfaces', 'ens3', 'ip6')] = [{'address': self.public_ipv6['address'], 'prefixLength': self.public_ipv6['prefixLength']}]
        if self.default_gateway6:
            networking['defaultGateway6'] = self.default_gateway6

        return Function("{ ... }", {
            'imports': [ RawValue('<nixpkgs/nixos/modules/profiles/qemu-guest.nix>') ],
            'networking': networking,
            ('boot', 'loader', 'grub', 'device'): 'nodev', # keep ubuntu bootloader?
            ('fileSystems', '/'): { 'device': '/dev/vda1', 'fsType': 'ext4'},
            ('users', 'extraUsers', 'root', 'openssh', 'authorizedKeys', 'keys'): [self.depl.active_resources.get('ssh-key').public_key],
        })

    def get_ssh_private_key_file(self):
        return self.write_ssh_private_key(self.depl.active_resources.get('ssh-key').private_key)

    def create_after(self, resources, defn):
        # make sure the ssh key exists before we do anything else
        return {
            r for r in resources if
            isinstance(r, nixops.resources.ssh_keypair.SSHKeyPairState)
        }

    def get_auth_token(self):
        return os.environ.get('DIGITAL_OCEAN_AUTH_TOKEN', self.auth_token)

    def destroy(self, wipe=False):
        self.log("destroying droplet {}".format(self.droplet_id))
        try:
            droplet = digitalocean.Droplet(id=self.droplet_id, token=self.get_auth_token())
            droplet.destroy()
        except digitalocean.baseapi.NotFoundError:
            self.log("droplet not found - assuming it's been destroyed already")
        self.public_ipv4 = None
        self.droplet_id = None

        return True

    def create(self, defn, check, allow_reboot, allow_recreate):
        ssh_key = self.depl.active_resources.get('ssh-key')
        if ssh_key is None:
            raise Exception('Please specify a ssh-key resource (resources.sshKeyPairs.ssh-key = {}).')

        self.set_common_state(defn)

        if self.droplet_id is not None:
            return

        self.manager = digitalocean.Manager(token=self.get_auth_token())
        droplet = digitalocean.Droplet(
            token=self.get_auth_token(),
            name=self.name,
            region=defn.region,
            ipv6=defn.enable_ipv6,
            ssh_keys=[ssh_key.public_key],
            image='ubuntu-16-04-x64', # only for lustration
            size_slug=defn.size,
        )

        self.log_start("creating droplet ...")
        droplet.create()

        status = 'in-progress'
        while status == 'in-progress':
            actions = droplet.get_actions()
            for action in actions:
                action.load()
                if action.status != 'in-progress':
                    status = action.status
            time.sleep(1)
            self.log_continue("[{}] ".format(status))

        if status != 'completed':
            raise Exception("unexpected status: {}".format(status))

        droplet.load()
        self.droplet_id = droplet.id
        self.public_ipv4 = droplet.ip_address
        self.log_end("{}".format(droplet.ip_address))

        # Not sure when I'd have more than one interface from the DO
        # API but networks is an array nevertheless.
        self.default_gateway = droplet.networks['v4'][0]['gateway']
        self.netmask = droplet.networks['v4'][0]['netmask']

        first_ipv6 = {}
        first_gw6 = None
        if 'v6' in droplet.networks:
            public_ipv6_networks = [n for n in droplet.networks['v6'] if n['type'] == 'public']
            if len(public_ipv6_networks) > 0:
                # The DigitalOcean API does not expose an explicit
                # default interface or gateway, so assume this is it.
                first_ipv6['address'] = public_ipv6_networks[0]['ip_address']
                first_ipv6['prefixLength'] = public_ipv6_networks[0]['netmask']
                first_gw6 = public_ipv6_networks[0]['gateway']
        self.public_ipv6 = first_ipv6
        self.default_gateway6 = first_gw6

        # run modified nixos-infect
        # - no reboot
        # - predictable network interface naming (ens3 etc)
        self.wait_for_ssh()
        self.log_start("running nixos-infect")
        self.run_command('bash </dev/stdin 2>&1', stdin=open(infect_path))
        self.reboot_sync()

    def reboot(self, hard=False):
        if hard:
            self.log("sending hard reset to droplet...")
            droplet = digitalocean.Droplet(id=self.droplet_id, token=self.get_auth_token())
            droplet.reboot()
            self.wait_for_ssh()
            self.state = self.STARTING
        else:
            MachineState.reboot(self, hard=hard)

