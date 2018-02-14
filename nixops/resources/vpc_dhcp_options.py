# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPC DHCP options.

import os
import json

import boto3
import botocore

import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
import nixops.ec2_utils
from nixops.state.state_helper import StateDict
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

class VPCDhcpOptionsState(nixops.resources.DiffEngineResourceState, EC2CommonState):
    """State of a VPC DHCP options."""

    state = nixops.util.attr_property("state", nixops.resources.DiffEngineResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ['dhcpOptionsId']

    @classmethod
    def get_type(cls):
        return "vpc-dhcp-options"

    def __init__(self, depl, name, id):
        nixops.resources.DiffEngineResourceState.__init__(self, depl, name, id)
        self._state = StateDict(depl, id)
        handled_keys=['region', 'vpcId', 'domainNameServers', 'domainName', 'ntpServers', 'netbiosNameServers', 'netbiosNodeType']
        self.handle_create_dhcp_options = Handler(handled_keys, handle=self.realize_create_dhcp_options)
        self.handle_tag_update = Handler(['tags'], after=[self.handle_create_dhcp_options], handle=self.realize_update_tag)

    def show_type(self):
        s = super(VPCDhcpOptionsState, self).show_type()
        region = self._state.get('region', None)
        if region: s = "{0} [{1}]".format(s, region)
        return s

    @property
    def resource_id(self):
        return self._state.get('dhcpOptionsId', None)

    def prefix_definition(self, attr):
        return {('resources', 'vpcDhcpOptions'): attr}

    def get_physical_spec(self):
        return {}

    def get_definition_prefix(self):
        return "resources.vpcDhcpOptions."

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

    def realize_create_dhcp_options(self, allow_recreate):
        config = self.get_defn()
        if self.state == (self.UP or self.STARTING):
            if not allow_recreate:
                raise Exception("to recreate the dhcp options please add --allow-recreate"
                                " to the deploy command")
            self.warn("the dhcp options {} will be destroyed and re-created")
            self._destroy()

        self._state['region'] = config['region']
        vpc_id = config['vpcId']
        if vpc_id.startswith("res-"):
            res = self.depl.get_typed_resource(vpc_id[4:].split(".")[0], "vpc")
            vpc_id = res._state['vpcId']

        dhcp_config = self.generate_dhcp_configuration(config)

        def create_dhcp_options(dhcp_config):
            self.log("creating dhcp options...")
            response = self.get_client().create_dhcp_options(DhcpConfigurations=dhcp_config)
            return response.get('DhcpOptions').get('DhcpOptionsId')

        dhcp_options_id = create_dhcp_options(dhcp_config)
        with self.depl._state.db:
            self.state = self.STARTING
            self._state['vpcId'] = vpc_id
            self._state['dhcpOptionsId'] = dhcp_options_id
            self._state['domainName'] = config["domainName"]
            self._state['domainNameServers'] = config["domainNameServers"]
            self._state['ntpServers'] = config["ntpServers"]
            self._state['netbiosNameServers'] = config["netbiosNameServers"]
            self._state['netbiosNodeType'] = config["netbiosNodeType"]

        self.get_client().associate_dhcp_options(DhcpOptionsId=dhcp_options_id, VpcId=vpc_id)
        with self.depl._state.db:
            self.state = self.UP

    def realize_update_tag(self, allow_recreate):
        config = self.get_defn()
        tags = config['tags']
        tags.update(self.get_common_tags())
        self.get_client().create_tags(Resources=[self._state['dhcpOptionsId']], Tags=[{"Key": k, "Value": tags[k]} for k in tags])

    def _destroy(self):
        if self.state != self.UP: return
        dhcp_options_id = self._state.get('dhcpOptionsId', None)
        if dhcp_options_id:
            self.log("deleting dhcp options {0}".format(dhcp_options_id))
            try:
                self.get_client().associate_dhcp_options(DhcpOptionsId='default', VpcId=self._state['vpcId'])
                self.get_client().delete_dhcp_options(DhcpOptionsId=dhcp_options_id)
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] == 'InvalidDhcpOptionsID.NotFound':
                    self.warn("dhcp options {0} was already deleted".format(dhcp_options_id))
                else:
                    raise e

            with self.depl._state.db:
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
