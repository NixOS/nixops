# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPC DHCP options.

import json

import boto3
import botocore

import nixops.util
import nixops.resources
import nixops.resources.ec2_common
import nixops.ec2_utils

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
    region = nixops.util.attr_property("region", None)
    vpc_id = nixops.util.attr_property("vpcId", None)
    dhcp_options_id = nixops.util.attr_property("dhcpOptions", None)
    domain_name = nixops.util.attr_property("domainName", None)
    domain_name_servers = nixops.util.attr_property("domainNameServers", [], 'json')
    ntp_servers = nixops.util.attr_property("ntpServers", [], 'json')
    netbios_name_servers = nixops.util.attr_property("netbiosNameServers", [], 'json')
    netbios_node_type = nixops.util.attr_property("netbiosNodeType", None, int)

    @classmethod
    def get_type(cls):
        return "vpc-dhcp-options"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._client = None

    def show_type(self):
        s = super(VPCDhcpOptionsState, self).show_type()
        if self.region: s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return self.dhcp_options_id

    def prefix_definition(self, attr):
        return {('resources', 'vpcDhcpOptions'): attr}

    def get_physical_spec(self):
        return {}

    def get_definition_prefix(self):
        return "resources.vpcDhcpOptions."

    def connect(self):
        if self._client: return
        assert self.region
        (access_key_id, secret_access_key) = nixops.ec2_utils.fetch_aws_secret_key(self.access_key_id)
        self._client = boto3.client('ec2', region_name=self.region, aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)

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
        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        self.region = defn.config['region']

        self.connect()

        vpc_id = defn.config['vpcId']
        dhcp_options_id = self.dhcp_options_id

        if vpc_id.startswith("res-"):
            res = self.depl.get_typed_resource(vpc_id[4:], "vpc")
            vpc_id = res.vpc_id

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
            if (defn.config['domainName'] != self.domain_name or
                json.dumps(defn.config['domainNameServers']) != json.dumps(self.domain_name_servers) or
                json.dumps(defn.config['ntpServers']) != json.dumps(self.ntp_servers) or
                json.dumps(defn.config['netbiosNameServers']) != json.dumps(self.netbios_name_servers) or
                defn.config['netbiosNodeType'] != self.netbios_node_type):
                if allow_recreate:
                    dhcp_options_id = create_dhcp_options(dhcp_config)
                    self._client.associate_dhcp_options(DhcpOptionsId=dhcp_options_id, VpcId=vpc_id)
                    self._destroy()
                else:
                    raise Exception("the dhcp options need to be recreated for the requested changes; please run with --allow-recreate")

        with self.depl._db:
            self.state = self.UP
            self.vpc_id = vpc_id
            self.dhcp_options_id = dhcp_options_id
            self.domain_name = defn.config["domainName"]
            self.domain_name_servers = defn.config["domainNameServers"]
            self.ntp_servers = defn.config["ntpServers"]
            self.netbios_name_servers = defn.config["netbiosNameServers"]
            self.netbios_node_type = defn.config["netbiosNodeType"]

    def _destroy(self):
        if self.state != self.UP: return
        self.log("deleting dhcp options {0}".format(self.dhcp_options_id))
        self.connect()
        try:
            self._client.associate_dhcp_options(DhcpOptionsId='default', VpcId=self.vpc_id)
            self._client.delete_dhcp_options(DhcpOptionsId=self.dhcp_options_id)
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'InvalidDhcpOptionsID.NotFound':
                self.warn("dhcp options {0} was already deleted".format(self.dhcp_options_id))
            else:
                raise e

        with self.depl._db:
            self.state = self.MISSING
            self.vpc_id = None
            self.dhcp_options_id = None
            self.domain_name = None
            self.domain_name_servers = None
            self.ntp_servers = None
            self.netbios_name_servers = None
            self.netbios_node_type = None


    def destroy(self, wipe=False):
        self._destroy()
        return True
