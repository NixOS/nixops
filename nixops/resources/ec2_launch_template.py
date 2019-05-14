# -*- coding: utf-8 -*-
import nixops.util
import nixops.resources
import botocore.exceptions
from nixops.resources.ec2_common import EC2CommonState

class ec2LaunchTemplateDefinition(nixops.resources.ResourceDefinition):
    """Definition of an ec2 fleet"""

    @classmethod
    def get_type(cls):
        return "ec2-launch-template"

    @classmethod
    def get_resource_type(cls):
        return "ec2LaunchTemplate"

    def show_type(self):
        return "{0}".format(self.get_type())


class ec2LaunchTemplate(nixops.resources.ResourceState, EC2CommonState):
    """State of an ec2 launch template"""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    region = nixops.util.attr_property("region", None)
    name = nixops.util.attr_property("LTName", None)
    templateId = nixops.util.attr_property("templateId", None)
    LTdescription = nixops.util.attr_property("LTdescription", None)
    version = nixops.util.attr_property("LTVersion", None)
    versionDescription = nixops.util.attr_property("LTVersionDescription", None)
    ebsOptimized = nixops.util.attr_property("LTEbsOptimized", True, type=bool)
    instanceProfile = nixops.util.attr_property("LTInstanceProfile", None)
    imageId = nixops.util.attr_property("LTImageId", None)
    instanceType = nixops.util.attr_property("LTInstanceType", None)
    keyName = nixops.util.attr_property("LTKeyName", None)
    userData = nixops.util.attr_property("LTUserData", None)
    securityGroupIds = nixops.util.attr_property("LTSecurityGroupIds", None, 'json')
    disableApiTermination = nixops.util.attr_property("LTDisableApiTermination", False, type=bool)
    instanceInitiatedShutdownBehavior = nixops.util.attr_property("LTInstanceInitiatedShutdownBehavior", None)
    placementGroup = nixops.util.attr_property("LTPlacementGroup", None)
    availabilityZone = nixops.util.attr_property("LTAvailabilityZone", None)
    tenancy = nixops.util.attr_property("LTTenancy", None)
    associatePublicIpAddress = nixops.util.attr_property("LTAssociatePublicIpAddress", True, type=bool)
    networkInterfaceId = nixops.util.attr_property("LTNetworkInterfaceId", None)
    subnetId = nixops.util.attr_property("LTSubnetId", None)
    privateIpAddresses = nixops.util.attr_property("LTPrivateIpAddresses", {}, 'json')
    secondaryPrivateIpAddressCount = nixops.util.attr_property("LTSecondaryPrivateIpAddressCount", None)
    monitoring = nixops.util.attr_property("LTMonitoring", False, type=bool)
    instanceMarketOptions = nixops.util.attr_property("LTInstanceMarketOptions", {}, 'json')
    clientToken = nixops.util.attr_property("LTClientToken", None)

    @classmethod
    def get_type(cls):
        return "ec2-launch-template"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._conn_boto3 = None

    def _exists(self):
        return self.state != self.MISSING

    def show_type(self):
        s = super(ec2LaunchTemplate, self).show_type()
        return s

    @property
    def resource_id(self):
        return self.templateId

    def connect_boto3(self, region):
        if self._conn_boto3: return self._conn_boto3
        self._conn_boto3 = nixops.ec2_utils.connect_ec2_boto3(region, self.access_key_id)
        return self._conn_boto3

    def create(self, defn, check, allow_reboot, allow_recreate):

        if self.region is None:
            self.region = defn.config['region']
        elif self.region != defn.config['region']:
            self.warn("cannot change region of a running instance (from ‘{}‘ to ‘{}‘)".format(self.region, defn.config['region']))

        self.access_key_id = defn.config['accessKeyId']
        self.connect_boto3(self.region)

        # Create the fleet dict request.
        if self.state != self.UP: 
            args = dict()
            
            # Use a client token to ensure that fleet creation is
            # idempotent; i.e., if we get interrupted before recording
            # the fleet ID, we'll get the same fleet ID on the
            # next run.
            if not self.clientToken:
                with self.depl._db:
                    self.clientToken = nixops.util.generate_random_string(length=48) # = 64 ASCII chars
                    #self.state = self.STARTING

            args['ClientToken'] = self.clientToken

            # fleet = self._retry(
            #     lambda: self._conn_boto3.create_fleet(**args)
            # )

            try:
                launch_template = self._conn_boto3.create_launch_template(**args)
            except botocore.exceptions.ClientError as error:
                raise error
                #TODO: handle IdempotentParameterMismatch
                # Not sure whether to use lambda retry or keep it like this
            with self.depl._db:
                self.state = self.STARTING
                self.templateId = fleet['FleetId']
            self.state = self.UP
    
    def check(self):

        # check default version and make sure it match the current version in the state
        self.connect_boto3(self.region)
        launch_template = self._conn_boto3.describe_launch_templates(
                    FleetIds=[self.templateId]
                   )['Fleets']
        if fleet is None:
            self.state = self.MISSING
            return

    def _destroy(self):

        self.connect_boto3(self.region)
        self.log("deleting ec2 launch template `{}`... ".format(self.name))
        try:
            self._conn_boto3.delete_launch_template(LaunchTemplateId=self.templateId)
        except botocore.exceptions.ClientError as error:
            # check if it is already deleted and say that it is
            raise error

    def destroy(self, wipe=False):
        if not self._exists(): return True

        self._destroy()
        return True


# when using maintain request type things will go above nixops so it is not like persistent spot
# we can show the instance ids and their ips in info 