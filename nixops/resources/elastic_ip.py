# -*- coding: utf-8 -*-

# Automatic provisioning of EC2 elastic IP addresses.

import time
import nixops.util
import nixops.resources
import nixops.ec2_utils


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


class ElasticIPState(nixops.resources.ResourceState):
    """State of an EC2 elastic IP address."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("ec2.accessKeyId", None)
    region = nixops.util.attr_property("ec2.region", None)
    public_ipv4 = nixops.util.attr_property("ec2.ipv4", None)
    allocation_id = nixops.util.attr_property("allocationId", None)
    vpc = nixops.util.attr_property("vpc", False, bool)


    @classmethod
    def get_type(cls):
        return "elastic-ip"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._client = None

    def show_type(self):
        s = super(ElasticIPState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return self.allocation_id

    def get_physical_spec(self):
        physical = {}
        if self.public_ipv4:
            physical['address'] = self.public_ipv4
        return physical

    def prefix_definition(self, attr):
        return {('resources', 'elasticIPs'): attr}

    def connect(self, region):
        if self._client:
            return
        self._client = nixops.ec2_utils.connect_ec2_boto3(region, self.access_key_id)

    def create(self, defn, check, allow_reboot, allow_recreate):

        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set ‘accessKeyId’, $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        if self.state == self.UP and (self.region != defn.config['region']):
            raise Exception("changing the region of an elastic IP address is not supported")

        if self.state != self.UP:

            self.connect(defn.config['region'])

            is_vpc = defn.config['vpc']
            domain = 'vpc' if is_vpc else 'standard'

            self.log("creating elastic IP address (region ‘{0}’ - domain ‘{1}’)...".format(defn.config['region'],domain))
            address = self._client.allocate_address(Domain=domain)

            # FIXME: if we crash before the next step, we forget the
            # address we just created.  Doesn't seem to be anything we
            # can do about this.

            with self.depl._db:
                self.state = self.UP
                self.region = defn.config['region']
                self.public_ipv4 = address['PublicIp']
                if is_vpc:
                    self.allocation_id = address['AllocationId']
                self.vpc = is_vpc

            self.log("IP address is {0}".format(self.public_ipv4))

    def describe_eip(self):
        try:
            response = self._client.describe_addresses(Filters=[{
                "Name":"public-ip",
                "Values":[self.public_ipv4]
                }])
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == "InvalidAddress.NotFound":
                self.warn("public IP {} was deleted".format(self.public_ipv4))
                return None
            else:
                raise error
        if len(response['Addresses']) == 0:
            self.warn("public IP {} was deleted".format(self.public_ipv4))
            return None
        return response['Addresses'][0]

    def destroy(self, wipe=False):
        if self.state == self.UP:
            self.connect(self.region)
            eip = self.describe_eip()
            vpc = (eip.get('Domain', None) == 'vpc')
            if eip is not None:
                if 'AssociationId' in eip.keys():
                    self.log("disassociating elastic ip {0} with assocation ID {1}".format(
                        eip['PublicIp'], eip['AssociationId']))
                    if vpc:
                        self._client.disassociate_address(AssociationId=eip['AssociationId'])
                self.log("releasing elastic IP {}".format(eip['PublicIp']))
                if vpc == True:
                    self._client.release_address(AllocationId=eip['AllocationId'])
                else:
                    self._client.release_address(PublicIp=eip['PublicIp'])

            with self.depl._db:
                self.state = self.MISSING
                self.public_ipv4 = None
                self.allocation_id = None
                self.vpc = None

        return True
