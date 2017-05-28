# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPC DHCP options.

import os
import json

import boto3
import botocore

import nixops.util
import nixops.resources
import nixops.resources.ec2_common
import nixops.ec2_utils
from nixops.state import StateDict
from nixops.diff import Diff, Handler

class VPCDhcpOptionsDefinition(nixops.resources.ResourceDefinition):
    """Definition of a VPC DHCP options."""

    @classmethod
    def get_type(cls):
        return "vpc-dhcp-options"

    @classmethod
    def get_resource_type(cls):
        return "vpcDhcpOptions"

    def show_type(self):
        return "{0}".format(self.get_type())


class VPCDhcpOptionsState(nixops.resources.ResourceState, nixops.resources.ec2_common.EC2CommonState):
    """State of a VPC DHCP options."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)

    @classmethod
    def get_type(cls):
        return "vpc-dhcp-options"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._client = None
        self._state = StateDict(depl, id)
        self._handler_calls = 0
        self.handle_config_change = Handler('domainNameServers', 'domainName', 'ntpServers'
                , 'netbiosNameServers', 'netbiosNodeType')

    def get_handlers(self):
        return [getattr(self,h) for h in dir(self) if isinstance(getattr(self,h), Handler)]

    def show_type(self):
        s = super(VPCDhcpOptionsState, self).show_type()
        region = self._state.get('region', None)
        if region: s = "{0} [{1}]".format(s, region)
        return s

    @property
    def resource_id(self):
        return self._state.get('dhcpOptions', None)

    def prefix_definition(self, attr):
        return {('resources', 'vpcDhcpOptions'): attr}

    def get_physical_spec(self):
        return {}

    def get_definition_prefix(self):
        return "resources.vpcDhcpOptions."

    def connect(self):
        if self._client: return
        assert self._state['region']
        (access_key_id, secret_access_key) = nixops.ec2_utils.fetch_aws_secret_key(self.access_key_id)
        self._client = boto3.client('ec2', region_name=self._state['region'], aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc.VPCState)}

    def get_dhcp_config_option(self, key, values):
        val = values if isinstance(values, list) else [ str(values) ]
        return {'Key': key, 'Values': val}

    def generate_dhcp_configuration(self, config):
        configuration = []

        def check_and_append(option, key):
            if config[option]:
                configuration.append(self.get_dhcp_config_option(key=key, values=config[option]))

        check_and_append('domainNameServers', 'domain-name-servers')
        check_and_append('domainName', 'domain-name')
        check_and_append('ntpServers', 'ntp-servers')
        check_and_append('netbiosNameServers', 'netbios-name-servers')
        check_and_append('netbiosNodeType', 'netbios-node-type')
        return configuration

    def create(self, defn, check, allow_reboot, allow_recreate):
        # declare handlers
        self.handle_config_change.handle = self.handle_change(config=defn.config)
        if os.environ.get('NIXOPS_PLAN'):
            diff = Diff(depl=self.depl, logger=self.logger, enable_handler=True,
                    config=defn.config, state=self._state, res_type=self.get_type())
            diff.set_handlers(self.get_handlers())
            diff.get_handlers_sequence()
            diff.set_reserved_keys(['dhcpOptions', 'accessKeyId'])
            diff.plan()

        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        self._state['region'] = defn.config['region']

        self.connect()

        vpc_id = defn.config['vpcId']
        dhcp_options_id = self._state.get('dhcpOptions', None)

        if vpc_id.startswith("res-"):
            res = self.depl.get_typed_resource(vpc_id[4:].split(".")[0], "vpc")
            vpc_id = res._state['vpcId']

        dhcp_config = self.generate_dhcp_configuration(defn.config)

        def create_dhcp_options(dhcp_config):
            self.log("creating dhcp options...")
            response = self._client.create_dhcp_options(DhcpConfigurations=dhcp_config)
            return response.get('DhcpOptions').get('DhcpOptionsId')

        if self.state != self.UP:
            dhcp_options_id = create_dhcp_options(dhcp_config)
            self.log("associating dhcp options {0} with vpc {1}".format(dhcp_options_id, vpc_id))
            self._client.associate_dhcp_options(DhcpOptionsId=dhcp_options_id, VpcId=vpc_id)

        if self.state == self.UP:
            if self._handler_calls > 0:
                if allow_recreate:
                    dhcp_options_id = create_dhcp_options(dhcp_config)
                    self._client.associate_dhcp_options(DhcpOptionsId=dhcp_options_id, VpcId=vpc_id)
                    self._destroy()
                else:
                    raise Exception("the dhcp options need to be recreated for the requested changes; please run with --allow-recreate")

        with self.depl._db:
            self.state = self.UP
            self._state['vpcId'] = vpc_id
            self._state['dhcpOptions'] = dhcp_options_id
            self._state['domainName'] = defn.config["domainName"]
            self._state['domainNameServers'] = defn.config["domainNameServers"]
            self._state['ntpServers'] = defn.config["ntpServers"]
            self._state['netbiosNameServers'] = defn.config["netbiosNameServers"]
            self._state['netbiosNodeType'] = defn.config["netbiosNodeType"]

    def handle_config_change(self, config):
        self.increment_handle_calls()

    def _destroy(self):
        if self.state != self.UP: return
        dhcp_options_id = self._state.get('dhcpOptions', None)
        if dhcp_options_id:
            self.log("deleting dhcp options {0}".format(dhcp_options_id))
            self.connect()
            try:
                self._client.associate_dhcp_options(DhcpOptionsId='default', VpcId=self._state['vpcId'])
                self._client.delete_dhcp_options(DhcpOptionsId=dhcp_options_id)
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] == 'InvalidDhcpOptionsID.NotFound':
                    self.warn("dhcp options {0} was already deleted".format(dhcp_options_id))
                else:
                    raise e

            with self.depl._db:
                self.state = self.MISSING
                self._state['vpcId'] = None
                self._state['dhcpOptions'] = None
                self._state['domainName'] = None
                self._state['domainNameServers'] = None
                self._state['ntpServers'] = None
                self._state['netbiosNameServers'] = None
                self._state['netbiosNodeType'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
