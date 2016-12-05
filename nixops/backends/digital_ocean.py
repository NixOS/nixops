# -*- coding: utf-8 -*-
"""
auto-loaded via _load_modules_from in deployment.py
"""
import os
import os.path
import sys
import re
import time
import math
import shutil
import nixops.resources
from nixops.backends import MachineDefinition, MachineState
from nixops.nix_expr import Function, Call, RawValue
import nixops.util
import nixops.known_hosts
from xml import etree
import datetime
import digitalocean
import socket

SSH_KEY = """ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEAtq8LpgrnFQWpIcK5YdrQNzu22sPrbkHKD83g8v/s7Nu3Omb7h5TLBOZ6DYPSorGMKGjDFqo0witXRagWq95HaA9epFXmhJlO3NTxyTAzIZSzql+oJkqszNpmYY09L00EIplE/YKXPlY2a+sGx3CdJxbglGfTcqf0J2DW4wO2ikZSOXRiLEbztyDwc+TNwYJ3WtzTFWhG/9hbbHGZtpwQl6X5l5d2Mhl2tlKJ/zQYWV1CVXLSyKhkb4cQPkL05enguCQgijuI/WsUE6pqdl4ypziXGjlHAfH+zO06s6EDMQYr50xgYRuCBicF86GF8/fOuDJS5CJ8/FWr16fiWLa2Aw== tom@leto"""

class DigitalOceanDefinition(MachineDefinition, nixops.resources.ResourceDefinition):
    @classmethod
    def get_type(cls):
        return "digital-ocean"

    def __init__(self, xml, config):
        MachineDefinition.__init__(self, xml, config)
        self.auth_token = config["digital-ocean"]["authToken"]
        self.region = config["digital-ocean"]["region"]
        self.size = config["digital-ocean"]["size"]
        self.key_name = config["digital-ocean"]["keyName"]

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region)


class DigitalOceanState(MachineState):
    @classmethod
    def get_type(cls):
        return "digital-ocean"

    state = nixops.util.attr_property("state", MachineState.MISSING, int)  # override
    public_ipv4 = nixops.util.attr_property("publicIpv4", None)
    default_gateway = nixops.util.attr_property("defaultGateway", None)
    public_dns_name = nixops.util.attr_property("publicDnsName", None)
    netmask = nixops.util.attr_property("netmask", None)
    region = nixops.util.attr_property("digital-ocean.region", None)
    size = nixops.util.attr_property("digital-ocean.size", None)
    key_name = nixops.util.attr_property("digital-ocean.keyName", None)
    auth_token = nixops.util.attr_property("digital-ocean.authToken", None)
    droplet_id = nixops.util.attr_property("digital-ocean.dropletId", None)

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)

    def get_ssh_name(self):
        print "SSH name",self.public_ipv4
        return self.public_ipv4

    def get_ssh_flags(self, *args, **kwargs):
        super_flags = super(DigitalOceanState, self).get_ssh_flags(*args, **kwargs)
        return super_flags + ['-o', 'UserKnownHostsFile=/dev/null', '-o', 'StrictHostKeyChecking=no']

    def get_physical_spec(self):
        prefixLength = bin(int(socket.inet_aton(self.netmask).encode('hex'), 16)).count('1')

        return Function("{ ... }", {
            'imports': [ RawValue('<nixpkgs/nixos/modules/profiles/qemu-guest.nix>') ],
            'networking': {
                'defaultGateway': self.default_gateway,
                ('interfaces', 'eth0'): {
                    'ip4': [{"address": self.public_ipv4, 'prefixLength': prefixLength}],
                },
            },
            ('boot', 'loader', 'grub', 'device'): '/dev/vda',
            ('fileSystems', '/'): { 'device': '/dev/vda1', 'fsType': 'ext4'},
            ('users', 'extraUsers', 'root', 'openssh', 'authorizedKeys', 'keys'): [SSH_KEY],
        })

    def get_ssh_private_key_file(self):
        return open('/home/tom/.ssh/id_rsa').read()

    def create_after(self, resources, defn):
        return set()

    def get_auth_token(self):
        return os.environ.get('DIGITAL_OCEAN_AUTH_TOKEN')

    def destroy(self, wipe=False):
        droplet = digitalocean.Droplet(id=self.droplet_id, token=self.get_auth_token())
        droplet.destroy()
        self.public_ipv4 = None
        self.droplet_id = None

    def create(self, defn, check, allow_reboot, allow_recreate):
        if self.droplet_id is not None:
            return

        """Create or update the resource defined by ‘defn’."""
        self.manager = digitalocean.Manager(token=self.get_auth_token())
        droplet = digitalocean.Droplet(
            token=self.get_auth_token(),
            name='Example',
            region=defn.region,
            ssh_keys=[SSH_KEY],
            image='ubuntu-14-04-x64', # only for lustration
            size_slug=defn.size,
        )
        droplet.create()

        status = 'in-progress'
        while status == 'in-progress':
            actions = droplet.get_actions()
            for action in actions:
                action.load()
                if action.status != 'in-progress':
                    status = action.status
            time.sleep(1)
        if status != 'completed':
            raise Exception("unexptected status: {}".format(status))

        droplet.load()
        self.droplet_id = droplet.id
        self.public_ipv4 = droplet.ip_address
        # TODO not sure when I'd have more than one interface?
        self.default_gateway = droplet.networks['v4'][0]['gateway']
        self.netmask = droplet.networks['v4'][0]['netmask']
        print "N", droplet.networks

        # N {u'v4': [{u'type': u'public', u'netmask': u'255.255.240.0', u'ip_address': u'138.197.32.239', u'gateway': u'138.197.32.1'}], u'v6': []}

        self.wait_for_ssh()

        self.run_command('curl https://raw.githubusercontent.com/elitak/nixos-infect/master/nixos-infect | bash 2>&1')


        self.reboot_sync()
