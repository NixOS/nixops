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

class VPCNetworkInterfaceState(nixops.resources.DiffEngineResourceState, EC2CommonState):
    """State of a VPC network interface"""

    state = nixops.util.attr_property("state", nixops.resources.DiffEngineResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ['networkInterfaceId']

    @classmethod
    def get_type(cls):
        return "vpc-network-interface"

    def __init__(self, depl, name, id):
        nixops.resources.DiffEngineResourceState.__init__(self, depl, name, id)
        self._state = StateDict(depl, id)
        self.region = self._state.get('region', None)
        self.handle_create_eni = Handler(['region', 'subnetId', 'primaryPrivateIpAddress',
                                          'privateIpAddresses', 'secondaryPrivateIpAddressCount'],
                                          handle=self.realize_create_eni)
        self.handle_modify_eni_attrs = Handler(['description', 'securityGroups', 'sourceDestCheck'],
                                               handle=self.realize_modify_eni_attrs,
                                               after=[self.handle_create_eni])
        self.handle_tag_update = Handler(['tags'], after=[self.handle_create_eni], handle=self.realize_update_tag)

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
        return { 'networkInterfaceId': self._state.get('networkInterfaceId', None) }

    def get_definition_prefix(self):
        return "resources.vpcNetworkInterfaces."

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc_subnet.VPCSubnetState)}

    def realize_create_eni(self, allow_recreate):
        config = self.get_defn()
        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("network interface {} definition changed and it needs to be recreated"
                                " use --allow-recreate if you want to create a new one".format(self._state['networkInterfaceId']))
            self.warn("network interface definition changed, recreating ...")
            self._destroy()

        self._state['region'] = config['region']

        eni_input = self.network_interface_input(config)
        self.log("creating vpc network interface under {}".format(eni_input['SubnetId']))
        response = self.get_client().create_network_interface(**eni_input)

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
            self._state['subnetId'] = eni_input['SubnetId']
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
        config = self.get_defn()
        self.log("applying network interface attribute changes")
        self.get_client().modify_network_interface_attribute(NetworkInterfaceId=self._state['networkInterfaceId'],
                                                        Description={'Value':config['description']})
        groups = []
        for grp in config['securityGroups']:
            if grp.startswith("res-"):
                res = self.depl.get_typed_resource(grp[4:].split(".")[0], "ec2-security-group")
                assert res.vpc_id
                groups.append(res.security_group_id)
            else:
                groups.append(grp)

        if len(groups) >= 1:
            self.get_client().modify_network_interface_attribute(
                NetworkInterfaceId=self._state['networkInterfaceId'],
                Groups=groups)

        self.get_client().modify_network_interface_attribute(NetworkInterfaceId=self._state['networkInterfaceId'],
                                                        SourceDestCheck={
                                                            'Value':config['sourceDestCheck']
                                                            })
        with self.depl._db:
            self._state['description'] = config['description']
            self._state['securityGroups'] = groups
            self._state['sourceDestCheck'] = config['sourceDestCheck']

    def realize_update_tag(self, allow_recreate):
        config = self.get_defn()
        tags = config['tags']
        tags.update(self.get_common_tags())
        self.get_client().create_tags(Resources=[self._state['networkInterfaceId']], Tags=[{"Key": k, "Value": tags[k]} for k in tags])

    def _destroy(self):
        if self.state != self.UP: return
        self.log("deleting vpc network interface {}".format(self._state['networkInterfaceId']))
        try:
            self.get_client().delete_network_interface(NetworkInterfaceId=self._state['networkInterfaceId'])
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == "InvalidNetworkInterfaceID.NotFound":
                self.warn("network interface {} was already deleted".format(self._state['networkInterfaceId']))
            else:
                raise e

        with self.depl._db:
            self.state = self.MISSING
            self._state['networkInterfaceId'] = None
            self._state['primaryPrivateIpAddress'] = None
            self._state['privateIpAddresses'] = None
            self._state['secondaryPrivateIpAddressCount'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
