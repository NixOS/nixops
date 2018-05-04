# -*- coding: utf-8 -*-
"""
A backend for hetzner cloud.

This backend uses nixos-infect (which uses nixos LUSTRATE) to infect a
hetzner cloud instance. The setup requires two reboots, one for
the infect itself, another after we pushed the nixos image.
"""
import os
import os.path
import time
import socket

import requests

import nixops.resources
from nixops.backends import MachineDefinition, MachineState
from nixops.nix_expr import Function, RawValue
import nixops.util
import nixops.known_hosts

infect_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'nixos-infect'))

API_HOST = 'api.hetzner.cloud'

class ApiError(Exception):
    pass

class ApiNotFoundError(ApiError):
    pass

class HetznerCloudDefinition(MachineDefinition):
    @classmethod
    def get_type(cls):
        return "hetznerCloud"

    def __init__(self, xml, config):
        MachineDefinition.__init__(self, xml, config)
        self.auth_token = config["hetznerCloud"]["authToken"]
        self.location = config["hetznerCloud"]["location"]
        self.datacenter = config["hetznerCloud"]["datacenter"]
        self.server_type = config["hetznerCloud"]["serverType"]

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.location or self.datacenter or 'any location')


class HetznerCloudState(MachineState):
    @classmethod
    def get_type(cls):
        return "hetznerCloud"

    state = nixops.util.attr_property("state", MachineState.MISSING, int)  # override
    public_ipv4 = nixops.util.attr_property("publicIpv4", None)
    public_ipv6 = nixops.util.attr_property("publicIpv6", None)
    location = nixops.util.attr_property("hetznerCloud.location", None)
    datacenter = nixops.util.attr_property("hetznerCloud.datacenter", None)
    server_type = nixops.util.attr_property("hetznerCloud.serverType", None)
    auth_token = nixops.util.attr_property("hetznerCloud.authToken", None)
    server_id = nixops.util.attr_property("hetznerCloud.serverId", None, int)

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        self.name = name

    def get_ssh_name(self):
        return self.public_ipv4

    def get_ssh_flags(self, *args, **kwargs):
        super_flags = super(HetznerCloudState, self).get_ssh_flags(*args, **kwargs)
        return super_flags + [
            '-o', 'UserKnownHostsFile=/dev/null',
            '-o', 'StrictHostKeyChecking=no',
            '-i', self.get_ssh_private_key_file(),
        ]

    def get_physical_spec(self):
        return Function("{ ... }", {
            'imports': [ RawValue('<nixpkgs/nixos/modules/profiles/qemu-guest.nix>') ],
            ('boot', 'loader', 'grub', 'device'): 'nodev',
            ('fileSystems', '/'): { 'device': '/dev/sda1', 'fsType': 'ext4'},
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
        return os.environ.get('HETZNER_CLOUD_AUTH_TOKEN', self.auth_token)

    def _api(self, path, method=None, data=None, json=True):
        """Basic wrapper around requests that handles auth and serialization."""
        assert path[0] == '/'
        url = 'https://%s%s' % (API_HOST, path)
        token = self.get_auth_token()
        if not token:
            raise Exception('No hetzner cloud auth token set')
        headers = {
            'Authorization': 'Bearer '+self.get_auth_token(),
        }
        res = requests.request(
            method=method,
            url=url,
            json=data,
            headers=headers)

        if res.status_code == 404:
            raise ApiNotFoundError('Not Found: %r' % path)
        elif not res.ok:
            raise ApiError('Response for %s %s has status code %d: %s' % (method, path, res.status_code, res.content))
        if not json:
            return
        try:
            res_data = res.json()
        except ValueError as e:
            raise ApiError('Response for %s %s has invalid JSON (%s): %r' % (method, path, e, res.content))
        return res_data


    def destroy(self, wipe=False):
        if not self.server_id:
            self.log('server {} was never made'.format(self.name))
            return
        self.log('destroying server {} with id {}'.format(self.name, self.server_id))
        try:
            res = self._api('/v1/servers/%s' % (self.server_id), method='DELETE')
        except ApiNotFoundError:
            self.log("server not found - assuming it's been destroyed already")

        self.public_ipv4 = None
        self.server_id = None

        return True

    def _create_ssh_key(self, public_key):
        """Create or get an ssh key and return an id."""
        public_key = public_key.strip()
        res = self._api('/v1/ssh_keys', method='GET')
        name = 'nixops-%s-%s' % (self.depl.uuid, self.name)
        deletes = []
        for key in res['ssh_keys']:
            if key['public_key'].strip() == public_key:
                return key['id']
            if key['name'] == name:
                deletes.append(key['id'])
        for d in deletes:
            # This reply is empty, so don't decode json.
            self._api('/v1/ssh_keys/%d' % d, method='DELETE', json=False)
        res = self._api('/v1/ssh_keys', method='POST', data={
            'name': name,
            'public_key': public_key,
        })
        return res['ssh_key']['id']

    def create(self, defn, check, allow_reboot, allow_recreate):
        ssh_key = self.depl.active_resources.get('ssh-key')
        if ssh_key is None:
            raise Exception('Please specify a ssh-key resource (resources.sshKeyPairs.ssh-key = {}).')

        self.set_common_state(defn)

        if self.server_id is not None:
            return

        ssh_key_id = self._create_ssh_key(ssh_key.public_key)

        req = {
                'name': self.name,
                'server_type': defn.server_type,
                'start_after_create': True,
                'image': 'debian-9',
                'ssh_keys': [
                    ssh_key_id,
                ],
        }

        if defn.datacenter:
            req['datacenter'] = defn.datacenter
        elif defn.location:
            req['location'] = defn.location

        self.log_start("creating server ...")
        create_res = self._api('/v1/servers', method='POST', data=req)
        self.server_id = create_res['server']['id']
        self.public_ipv4 = create_res['server']['public_net']['ipv4']['ip']
        self.public_ipv6 = create_res['server']['public_net']['ipv6']['ip']
        self.datacenter = create_res['server']['datacenter']['name']
        self.location = create_res['server']['datacenter']['location']['name']

        action = create_res['action']
        action_path = '/v1/servers/%d/actions/%d' % (self.server_id, action['id'])

        while action['status'] == 'running':
            time.sleep(1)
            res = self._api(action_path, method='GET')
            action = res['action']

        if action['status'] != 'success':
            raise Exception('unexpected status: %s' % action['status'])

        self.log_end("{}".format(self.public_ipv4))

        self.wait_for_ssh()
        self.log_start("running nixos-infect")
        self.run_command('bash </dev/stdin 2>&1', stdin=open(infect_path))
        self.reboot_sync()

    def reboot(self, hard=False):
        if hard:
            self.log("sending hard reset to server...")
            res = self._api('/v1/servers/%d/actions/reset' % self.server_id, method='POST')
            action = res['action']
            action_path = '/v1/servers/%d/actions/%d' % (self.server_id, action['id'])
            while action['status'] == 'running':
                time.sleep(1)
                res = self._api(action_path, method='GET')
                action = res['action']
            if action['status'] != 'success':
                raise Exception('unexpected status: %s' % action['status'])
            self.wait_for_ssh()
            self.state = self.STARTING
        else:
            MachineState.reboot(self, hard=hard)
