# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPC network interfaces.

import boto3
import botocore

import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
import nixops.ec2_utils
from nixops.diff import Diff, Handler
from nixops.state import StateDict

class VPCNetworkInterfaceDefinition(nixops.resources.ResourceDefinition):
    """Definition of a VPC network interface"""

    @classmethod
    def get_type(cls):
        return "vpc-network-interface"

    @classmethod
    def get_resource_type(cls):
        return "vpcNetworkInterfaces"

    def show_type(self):
        return "{0}".format(self.get_type())

class VPCNetworkInterfaceState(nixops.resources.ResourceState, EC2CommonState):
    """State of a VPC network interface"""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ['networkInterfaceId']

    @classmethod
    def get_type(cls):
        return "vpc-network-interface"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._client = None
        self._state = StateDict(depl, id)
        self.region = self._state.get('region', None)
        self.handle_create_eni = Handler(['region', 'subnetId', 'primaryPrivateIpAddress',
                                          'privateIpAddresses', 'secondaryPrivateIpAddressCount'],
                                          handle=self.realize_create_eni)
        self.handle_modify_eni_attrs = Handler(['description', 'securityGroups', 'attachements'],
                                               handle=self.realize_modify_eni_attrs,
                                               after=[self.handle_create_eni])

    def show_type(self):
        s = super(VPCNetworkInterfaceState, self).show_type()
        if self.region: s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return self._state.get('networkInterfaceId', None)

    def prefix_definition(self, attr):
        return {('resources', 'vpcNetworkInterfaces'): attr}

    def get_physical_spec(self):
        return { 'natGatewayId': self._state.get('networkInterfaceId', None) }

    def get_definition_prefix(self):
        return "resources.vpcNetworkInterfaces."

    def connect(self):
        if self._client: return
        self._client = nixops.ec2_utils.connect_ec2_boto3(self._state['region'], self.access_key_id)

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc_subnet.VPCSubnetState)}

    def create(self, defn, check, allow_reboot, allow_recreate):
        diff_engine = self.setup_diff_engine(config=defn.config)

        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        for handler in diff_engine.plan():
            handler.handle(allow_recreate)

    def realize_create_eni(self, allow_recreate):
        config = self.get_defn()
        self._state['region'] = config['region']
        self.connect()

        eni_input = self.network_interface_input(config)
        self.log("creating vpc network interface under {}".format(eni_input['SubnetId']))
        response = self._client.create_network_interface(**eni_input)

        eni = response['NetworkInterface']

        def split_ips(eni_ips):
            seconday = []
            for ip in eni_ips:
                if ip['Primary']:
                    primary = ip['PrivateIpAddress']
                else:
                    seconday.append(ip['PrivateIpAddress'])
            return primary, seconday

        primary, secondary = split_ips(eni['PrivateIpAddresses'])

        with self.depl._db:
            self.state = self.UP
            self._state['networkInterfaceId'] = eni['NetworkInterfaceId']
            self._state['primaryPrivateIpAddress'] = primary
            self._state['privateIpAddresses'] = secondary
            self._state['secondaryPrivateIpAddressCount'] = config['secondaryPrivateIpAddressCount']

    def network_interface_input(self, config):
        subnet_id = config['subnetId']
        if subnet_id.startswith("res-"):
            res = self.depl.get_typed_resource(subnet_id[4:].split(".")[0], "vpc-subnet")
            subnet_id = res._state['subnetId']

        groups = []
        for grp in config['securityGroups']:
            if grp.startswith("res-"):
                res = self.depl.get_typed_resource(grp[4:].split(".")[0], "ec2-security-group")
                assert res.vpc_id
                groups.append(res.security_group_id)
            else:
                groups.append(grp)

        primary_ip = config['primaryPrivateIpAddress']
        secondary_private_ips = config['privateIpAddresses']
        secondary_ip_count = config['secondaryPrivateIpAddressCount']
        if (primary_ip and len(secondary_private_ips) > 0) and secondary_ip_count:
            raise Exception("you can't set privateIpAddresses/primaryPrivateIpAddress options together"
                            " with secondaryPrivateIpAddressCount")
        ips = []
        if primary_ip:
            ips.append({'Primary':True, 'PrivateIpAddress':primary_ip})
        if len(secondary_private_ips) > 0:
            for ip in secondary_private_ips:
                ips.append({'Primary':False, 'PrivateIpAddress':ip})

        cfg = dict()
        cfg['Description'] = config['description']
        cfg['Groups'] = groups
        cfg['SubnetId'] = subnet_id
        if not secondary_ip_count:
            cfg['PrivateIpAddresses'] = ips
        else:
            cfg['secondaryPrivateIpAddressCount'] = secondary_ip_count

        return cfg

    def realize_modify_eni_attrs(self, allow_recreate):
        return True

    def _destroy(self):
        if self.state != self.UP: return
        self.log("deleting vpc network interface {}".format(self._state['networkInterfaceId']))
        self.connect()
        try:
            self._client.delete_network_interface(NetworkInterfaceId=self._state['networkInterfaceId'])
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == "InvalidNetworkInterfaceID.NotFound":
                self.warn("network interface {} was already deleted".format(self._state['networkInterfaceId']))
            else:
                raise e

        with self.depl._db:
            self.state = self.UP
            self._state['networkInterfaceId'] = None
            self._state['primaryPrivateIpAddress'] = None
            self._state['privateIpAddresses'] = None
            self._state['secondaryPrivateIpAddressCount'] = None

    def destroy(self, wipe=False):
        self._destroy()
