# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPC subnets.

import boto3
import botocore

import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
import nixops.ec2_utils
from nixops.diff import Diff, Handler
from nixops.state import StateDict

class VPCSubnetDefinition(nixops.resources.ResourceDefinition):
    """Definition of a VPC subnet."""

    @classmethod
    def get_type(cls):
        return "vpc-subnet"

    @classmethod
    def get_resource_type(cls):
        return "vpcSubnets"

    def show_type(self):
        return "{0}".format(self.get_type())


class VPCSubnetState(nixops.resources.DiffEngineResourceState, EC2CommonState):
    """State of a VPC subnet."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ['subnetId', 'associationId']

    @classmethod
    def get_type(cls):
        return "vpc-subnet"

    def __init__(self, depl, name, id):
        nixops.resources.DiffEngineResourceState.__init__(self, depl, name, id)
        self.subnet_id = self._state.get('subnetId', None)
        self.zone = self._state.get('zone', None)
        self.handle_create_subnet = Handler(['region', 'zone', 'cidrBlock', 'vpcId'], handle=self.realize_create_subnet)
        self.handle_map_public_ip_on_launch = Handler(['mapPublicIpOnLaunch'],
                                                      after=[self.handle_create_subnet],
                                                      handle=self.realize_map_public_ip_on_launch)
        self.handle_associate_ipv6_cidr_block = Handler(
            ['ipv6CidrBlock'],
            after=[self.handle_create_subnet],
            handle=self.realize_associate_ipv6_cidr_block)
        self.handle_tag_update = Handler(['tags'], after=[self.handle_create_subnet], handle=self.realize_update_tag)

    def show_type(self):
        s = super(VPCSubnetState, self).show_type()
        if self.zone: s = "{0} [{1}]".format(s, self.zone)
        return s

    @property
    def resource_id(self):
        return self.subnet_id

    def prefix_definition(self, attr):
        return {('resources', 'vpcSubnets'): attr}

    def get_physical_spec(self):
        return {'subnetId': self.subnet_id}

    def get_definition_prefix(self):
        return "resources.vpcSubnets."

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc.VPCState)}

    def create(self, defn, check, allow_reboot, allow_recreate):
        nixops.resources.DiffEngineResourceState.create(self, defn, check, allow_reboot, allow_recreate)
        self.ensure_subnet_up(check)

    def ensure_subnet_up(self, check):
        config = self.get_defn()
        self._state['region'] = config['region']

        if self._state.get('subnetId', None):
            if check:
                try:
                    self.get_client().describe_subnets(SubnetIds=[self._state['subnetId']])
                except botocore.exceptions.ClientError as error:
                    if error.response['Error']['Code'] == 'InvalidSubnetID.NotFound':
                        self.warn("subnet {} was deleted from outside nixops,"
                                  " recreating ...".format(self._state['subnetId']))
                        allow_recreate = True
                        self.realize_create_subnet(allow_recreate)
                        self.realize_map_public_ip_on_launch(allow_recreate)
                    else:
                        raise error
            if self.state != self.UP:
                self.wait_for_subnet_available(self._state['subnetId'])

    def wait_for_subnet_available(self, subnet_id):
        while True:
            response = self.get_client().describe_subnets(SubnetIds=[subnet_id])
            if len(response['Subnets']) == 1:
                subnet = response['Subnets'][0]
                if subnet['State'] == "available":
                    break
                elif subnet['State'] != "pending":
                    raise Exception("subnet {0} is in an unexpected state {1}".format(
                        subnet_id, subnet['State']))
                self.log_continue(".")
                time.sleep(1)
            else:
                raise Exception("couldn't find subnet {}, please run deploy with --check".format(subnet_id))
        self.log_end(" done")

        with self.depl._db:
            self.state = self.UP

    def realize_create_subnet(self, allow_recreate):
        config = self.get_defn()
        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("subnet {} definition changed and it needs to be recreated"
                                " use --allow-recreate if you want to create a new one".format(
                                    self.subnet_id))
            self.warn("subnet definition changed, recreating...")
            self._destroy()

        self._state['region'] = config['region']

        vpc_id = config['vpcId']

        if vpc_id.startswith("res-"):
            res = self.depl.get_typed_resource(vpc_id[4:].split(".")[0], "vpc")
            vpc_id = res._state['vpcId']

        zone = config['zone'] if config['zone'] else ''
        self.log("creating subnet in vpc {0}".format(vpc_id))
        response = self.get_client().create_subnet(VpcId=vpc_id, CidrBlock=config['cidrBlock'],
                                              AvailabilityZone=zone)
        subnet = response.get('Subnet')
        self.subnet_id = subnet.get('SubnetId')
        self.zone = subnet.get('AvailabilityZone')

        with self.depl._db:
            self.state = self.STARTING
            self._state['subnetId'] = self.subnet_id
            self._state['cidrBlock'] = config['cidrBlock']
            self._state['zone'] = self.zone
            self._state['vpcId'] = vpc_id
            self._state['region'] = config['region']

        def tag_updater(tags):
            self.get_client().create_tags(Resources=[self.subnet_id],
                                     Tags=[{"Key": k, "Value": tags[k]} for k in tags])

        self.update_tags_using(tag_updater, user_tags=config["tags"], check=True)

        self.wait_for_subnet_available(self.subnet_id)

    def realize_map_public_ip_on_launch(self, allow_recreate):
        config = self.get_defn()
        self.get_client().modify_subnet_attribute(
            MapPublicIpOnLaunch={'Value':config['mapPublicIpOnLaunch']},
            SubnetId=self.subnet_id)

        with self.depl._db:
            self._state['mapPublicIpOnLaunch'] = config['mapPublicIpOnLaunch']

    def realize_associate_ipv6_cidr_block(self, allow_recreate):
        config = self.get_defn()

        if config['ipv6CidrBlock'] is not None:
            self.log("associating ipv6 cidr block {}".format(config['ipv6CidrBlock']))
            response = self.get_client().associate_subnet_cidr_block(
                Ipv6CidrBlock=config['ipv6CidrBlock'],
                SubnetId=self._state['subnetId'])
        else:
            self.log("disassociating ipv6 cidr block")
            self.get_client().disassociate_subnet_cidr_block(
                AssociationId=self._state['associationId'])

        with self.depl._db:
            self._state["ipv6CidrBlock"] = config['ipv6CidrBlock']
            if config['ipv6CidrBlock'] is not None:
                self._state['associationId'] = response['Ipv6CidrBlockAssociation']['AssociationId']

    def realize_update_tag(self, allow_recreate):
        config = self.get_defn()
        tags = config['tags']
        tags.update(self.get_common_tags())
        self.get_client().create_tags(Resources=[self._state['subnetId']], Tags=[{"Key": k, "Value": tags[k]} for k in tags])

    def _destroy(self):
        if self.state != (self.UP or self.STARTING): return
        self.log("deleting subnet {0}".format(self.subnet_id))
        try:
            #FIXME setting automatic retries for what it looks like AWS
            #eventual consistency issues but need to check further.
            self._retry(lambda: self.get_client().delete_subnet(SubnetId=self.subnet_id))
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == 'InvalidSubnetID.NotFound':
                self.warn("subnet {} was already deleted".format(self.subnet_id))
            else:
                raise error

        with self.depl._db:
            self.state = self.MISSING
            self._state['subnetID'] = None
            self._state['region'] = None
            self._state['vpcId'] = None
            self._state['cidrBlock'] = None
            self._state['zone'] = None
            self._state['mapPublicIpOnLaunch'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
