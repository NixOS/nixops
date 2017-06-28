# -*- coding: utf-8 -*-

# Automatic provisioning of EC2 elastic IP addresses.

import time

import nixops.util
import nixops.resources
import nixops.ec2_utils
from nixops.diff import Diff, Handler
from nixops.state import StateDict


class ElasticIPDefinition(nixops.resources.ResourceDefinition):
    """Definition of an EC2 elastic IP address."""

    @classmethod
    def get_type(cls):
        return "elastic-ip"

    @classmethod
    def get_resource_type(cls):
        return "elasticIPs"

    def show_type(self):
        return "{0}".format(self.get_type())


class ElasticIPState(nixops.resources.ResourceState, nixops.resources.ec2_common.EC2CommonState):
    """State of an EC2 elastic IP address."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = ['address', 'publicIPv4', 'allocationId', 'tags', 'ec2.tags', 'accessKeyId']

    @classmethod
    def get_type(cls):
        return "elastic-ip"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._client = None
        self._state = StateDict(depl, id)
        self._config = None
        self.region = self._state.get('region', None)
        self.handle_create_eip = Handler(['vpc', 'region'])
        self.handle_create_eip.handle = self.realize_create_eip

    def show_type(self):
        s = super(ElasticIPState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return self._state.get('publicIPv4', None)

    def connect(self):
        if self._client:
            return
        self._client = nixops.ec2_utils.connect_ec2_boto3(self._state['region'], self.access_key_id)

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set ‘accessKeyId’, $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        diff_engine = self.setup_diff_engine(config=defn.config)

        for handler in diff_engine.plan():
            handler.handle(defn, check, allow_reboot, allow_recreate)

    def realize_create_eip(self, defn, check, allow_reboot, allow_recreate):
        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("elastic IP {} definition changed"
                                " use --allow-recreate in order to deploy".format(self._state['publicIPv4']))
            self.warn("elastic IP definition changed, recreating...")
            self._destroy()
            self._client = None

        config = defn.config
        is_vpc = config['vpc']
        domain = 'vpc' if is_vpc else 'standard'
        self._state['region'] = config['region']
        self.connect()
        self.log("creating elastic IP address in region {0} - domain {1}"
                 .format(self._state['region'], domain))
        response = self._client.allocate_address(Domain=domain)

        with self.depl._db:
            self.state = self.UP
            self._state['publicIPv4'] = response['PublicIp']
            if is_vpc:
                self._state['allocationId'] = response['AllocationId']
            self._state['vpc'] = is_vpc

        self.log("IP address is {}".format(response['PublicIp']))

    def describe_eip(self):
        try:
            response = self._client.describe_addresses(Filters=[{
                "Name":"public-ip",
                "Values":[self._state["publicIPv4"]]
                }])
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == "InvalidAddress.NotFound":
                self.warn("public IP {} was deleted".format(self._state["publicIPv4"]))
            else:
                raise error
        return response['Addresses'][0]

    def destroy(self, wipe=False):
        if self.state == self.UP:
            vpc = self._state['vpc']
            self.connect()
            eip = self.describe_eip()
            if 'AssociationId' in eip.keys():
                self.log("disassociating elastic ip {0} with assocation ID {1}".format(
                    eip['PublicIp'], eip['AssociationId']))
                if vpc:
                    self._client.disassociate_address(AssociationId=eip['AssociationId'])
            self.log("releasing elastic IP {}".format(eip['PublicIp']))
            if vpc:
                self._client.release_address(AllocationId=eip['AllocationId'])
            else:
                self._client.release_address(PublicIp=eip['PublicIp'])

            with self.depl._db:
                self.state = self.MISSING
                self._state['publicIPv4'] = None
                self._state['allocationId'] = None
                self._state['vpc'] = None

        return True
