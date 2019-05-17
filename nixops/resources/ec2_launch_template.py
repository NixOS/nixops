# -*- coding: utf-8 -*-
import ast
import sys
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

class ec2LaunchTemplateState(nixops.resources.ResourceState, EC2CommonState):
    """State of an ec2 launch template"""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    region = nixops.util.attr_property("region", None)
    templateName = nixops.util.attr_property("LTName", None)
    templateId = nixops.util.attr_property("templateId", None)
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
        s = super(ec2LaunchTemplateState, self).show_type()
        return s

    @property
    def resource_id(self):
        return self.templateId

    def connect_boto3(self, region):
        if self._conn_boto3: return self._conn_boto3
        self._conn_boto3 = nixops.ec2_utils.connect_ec2_boto3(region, self.access_key_id)
        return self._conn_boto3


    def _update_tag(self, defn):
        self.connect_boto3(self.region)
        tags = defn.config['tags']
        tags.update(self.get_common_tags())
        self._conn_boto3.create_tags(Resources=[self.templateId], Tags=[{"Key": k, "Value": tags[k]} for k in tags])

    # TODO: Work on how to update the template (create a new version and update default version to use or what)
    # i think this is done automatically so i think i need to remove it right ?
    def create_after(self, resources, defn):
        # EC2 launch templates can require key pairs, IAM roles, security
        # groups and placement groups
        return {r for r in resources if
                isinstance(r, nixops.resources.ec2_keypair.EC2KeyPairState) or
                isinstance(r, nixops.resources.iam_role.IAMRoleState) or
                isinstance(r, nixops.resources.ec2_security_group.EC2SecurityGroupState) or
                isinstance(r, nixops.resources.ec2_placement_group.EC2PlacementGroupState) or
                isinstance(r, nixops.resources.vpc_subnet.VPCSubnetState)}

    def create(self, defn, check, allow_reboot, allow_recreate):

        if self.region is None:
            self.region = defn.config['region']
        elif self.region != defn.config['region']:
            self.warn("cannot change region of a running instance (from ‘{}‘ to ‘{}‘)"
                    .format(self.region, defn.config['region']))

        self.access_key_id = defn.config['accessKeyId']
        self.connect_boto3(self.region)
        if self.state != self.UP: 
            tags = defn.config['tags']
            tags.update(self.get_common_tags())
            args = dict()
            args['LaunchTemplateName'] = defn.config['name']
            args['VersionDescription'] = defn.config['versionDescription']
            args['LaunchTemplateData'] = dict(
                EbsOptimized=defn.config['LTData']['ebsOptimized'],
                ImageId=defn.config['LTData']['imageId'],
                Placement=dict(Tenancy=defn.config['LTData']['tenancy']),
                Monitoring=dict(Enabled=defn.config['LTData']['monitoring']),
                DisableApiTermination=defn.config['LTData']['disableApiTermination'],
                InstanceInitiatedShutdownBehavior=defn.config['LTData']['instanceInitiatedShutdownBehavior'],
                NetworkInterfaces=[dict(
                    DeviceIndex=0,
                    AssociatePublicIpAddress=defn.config['LTData']['associatePublicIpAddress']
                )],
                TagSpecifications=[dict(
                    ResourceType='instance',
                    Tags=[{"Key": k, "Value": tags[k]} for k in tags]
                ),
                dict(
                    ResourceType='volume',
                    Tags=[{"Key": k, "Value": tags[k]} for k in tags]
                ) ]
            )
            if defn.config['LTData']['instanceProfile'] != "":
                args['LaunchTemplateData']['IamInstanceProfile'] = dict(
                    Name=defn.config['LTData']['instanceProfile']
                )
            if defn.config['LTData']['userData']:
                args['LaunchTemplateData']['UserData'] = defn.config['LTData']['userData']

            if defn.config['LTData']['instanceType']:
                args['LaunchTemplateData']['InstanceType'] = defn.config['LTData']['instanceType']
            if defn.config['LTData']['securityGroupIds']!=[]:
                args['LaunchTemplateData']['SecurityGroupIds'] = defn.config['LTData']['securityGroupIds']
            if defn.config['LTData']['placementGroup'] != "":
                args['LaunchTemplateData']['Placement']['GroupName'] = defn.config['LTData']['placementGroup']
            if defn.config['LTData']['availabilityZone']:
                args['LaunchTemplateData']['Placement']['AvailabilityZone'] = defn.config['LTData']['availabilityZone']
            if defn.config['LTData']['instanceMarketOptions']:
                args['LaunchTemplateData']['InstanceMarketOptions'] = ast.literal_eval(defn.config['LTData']['instanceMarketOptions'])
            if defn.config['LTData']['subnetId'] == "" and defn.config['LTData']['networkInterfaceId'] == "":
                raise Exception("You must specify either a subnetId or a networkInterfaceId")
            if defn.config['LTData']['networkInterfaceId'] != "":
                args['LaunchTemplateData']['NetworkInterfaces'][0]['networkInterfaceId']=defn.config['LTData']['networkInterfaceId']
            if defn.config['LTData']['subnetId'] != "":
                args['LaunchTemplateData']['NetworkInterfaces'][0]['SubnetId']=defn.config['LTData']['subnetId']
            if defn.config['LTData']['secondaryPrivateIpAddressCount']:
                args['LaunchTemplateData']['NetworkInterfaces'][0]['SecondaryPrivateIpAddressCount']=defn.config['LTData']['secondaryPrivateIpAddressCount']
            if defn.config['LTData']['privateIpAddresses']:
                args['LaunchTemplateData']['NetworkInterfaces'][0]['PrivateIpAddresses']=defn.config['LTData']['privateIpAddresses']
            if defn.config['LTData']['keyName'] != "":
                args['LaunchTemplateData']['KeyName']=defn.config['LTData']['keyName']
            # TODO: work on tags.
            # Use a client token to ensure that fleet creation is
            # idempotent; i.e., if we get interrupted before recording
            # the fleet ID, we'll get the same fleet ID on the
            # next run.
            if not self.clientToken:
                with self.depl._db:
                    self.clientToken = nixops.util.generate_random_string(length=48) # = 64 ASCII chars
                    self.state = self.STARTING

            args['ClientToken'] = self.clientToken
            self.log("creating launch template {} ...".format(defn.config['name']))
            try:
                launch_template = self._conn_boto3.create_launch_template(**args)
            except botocore.exceptions.ClientError as error:
                raise error
                # Not sure whether to use lambda retry or keep it like this
            with self.depl._db:
                self.templateId = launch_template['LaunchTemplate']['LaunchTemplateId']
                self.templateName = defn.config['name']
                self.version = defn.config['version']
                self.versionDescription = defn.config['versionDescription']
                self.state = self.UP

            self._update_tag(defn)

    def check(self):

        self.connect_boto3(self.region)
        launch_template = self._conn_boto3.describe_launch_templates(
                    LaunchTemplateIds=[self.templateId]
                   )['LaunchTemplates']
        if launch_template is None:
            self.state = self.MISSING
            return
        if str(launch_template[0]['DefaultVersionNumber']) != self.version:
            self.warn("default version on the launch template is different then nixops managed version...") 

    def _destroy(self):

        self.connect_boto3(self.region)
        self.log("deleting ec2 launch template `{}`... ".format(self.templateName))
        try:
            self._conn_boto3.delete_launch_template(LaunchTemplateId=self.templateId)
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == "InvalidLaunchTemplateId.NotFound":
                self.warn("Template `{}` already deleted...".format(self.templateName))
            else:
                raise error

    def destroy(self, wipe=False):
        if not self._exists(): return True

        self._destroy()
        return True