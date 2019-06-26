# -*- coding: utf-8 -*-
import ast
import sys
import base64
import nixops.util
import nixops.ec2_utils
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
    templateName = nixops.util.attr_property("templateName", None)
    templateId = nixops.util.attr_property("templateId", None)
    templateVersion = nixops.util.attr_property("templateVersion", None)
    versionDescription = nixops.util.attr_property("versionDescription", None)
    ebsOptimized = nixops.util.attr_property("ebsOptimized", True, type=bool)
    instanceProfile = nixops.util.attr_property("instanceProfile", None)
    ami = nixops.util.attr_property("ami", None)
    instanceType = nixops.util.attr_property("instanceType", None)
    keyPair = nixops.util.attr_property("keyPair", None)
    userData = nixops.util.attr_property("userData", None)
    securityGroupIds = nixops.util.attr_property("securityGroupIds", None, 'json')
    disableApiTermination = nixops.util.attr_property("disableApiTermination", False, type=bool)
    instanceInitiatedShutdownBehavior = nixops.util.attr_property("instanceInitiatedShutdownBehavior", None)
    placementGroup = nixops.util.attr_property("placementGroup", None)
    zone = nixops.util.attr_property("zone", None)
    tenancy = nixops.util.attr_property("tenancy", None)
    associatePublicIpAddress = nixops.util.attr_property("associatePublicIpAddress", True, type=bool)
    networkInterfaceId = nixops.util.attr_property("networkInterfaceId", None)
    subnetId = nixops.util.attr_property("subnetId", None)
    privateIpAddresses = nixops.util.attr_property("privateIpAddresses", {}, 'json')
    secondaryPrivateIpAddressCount = nixops.util.attr_property("secondaryPrivateIpAddressCount", None)
    monitoring = nixops.util.attr_property("LTMonitoring", False, type=bool)
    spotInstancePrice = nixops.util.attr_property("ec2.spotInstancePrice", None)
    spotInstanceRequestType = nixops.util.attr_property("spotInstanceRequestType", None)
    spotInstanceInterruptionBehavior = nixops.util.attr_property("spotInstanceInterruptionBehavior", None)
    spotInstanceTimeout = nixops.util.attr_property("spotInstanceTimeout", None)
    clientToken = nixops.util.attr_property("clientToken", None)
    ebsInitialRootDiskSize = nixops.util.attr_property("ebsInitialRootDiskSize", None)

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

    # fix security group stuff later
    # def security_groups_to_ids(self, subnetId, groups):
        # sg_names = filter(lambda g: not g.startswith('sg-'), groups)
        # if sg_names != [ ] and subnetId != "":
            # self.connect_vpc()
            # vpc_id = self._conn_vpc.get_all_subnets([subnetId])[0].vpc_id
            # groups = map(lambda g: nixops.ec2_utils.name_to_security_group(self._conn, g, vpc_id), groups)

        # return groups

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
            args['LaunchTemplateName'] = defn.config['templateName']
            args['VersionDescription'] = defn.config['versionDescription']
            args['LaunchTemplateData'] = dict(
                EbsOptimized=defn.config['ebsOptimized'],
                ImageId=defn.config['ami'],
                Placement=dict(Tenancy=defn.config['tenancy']),
                Monitoring=dict(Enabled=defn.config['monitoring']),
                DisableApiTermination=defn.config['disableApiTermination'],
                InstanceInitiatedShutdownBehavior=defn.config['instanceInitiatedShutdownBehavior'],
                NetworkInterfaces=[dict(
                    DeviceIndex=0,
                    AssociatePublicIpAddress=defn.config['associatePublicIpAddress']
                )],
                # TagSpecifications=[dict(
                #     ResourceType='instance',
                #     Tags=[{"Key": k, "Value": tags[k]} for k in tags]
                # ),
                # dict(
                #     ResourceType='volume',
                #     Tags=[{"Key": k, "Value": tags[k]} for k in tags]
                # ) ]
            )
            if defn.config['instanceProfile'] != "":
                args['LaunchTemplateData']['IamInstanceProfile'] = dict(
                    Name=defn.config['instanceProfile']
                )
            if defn.config['userData']:
                args['LaunchTemplateData']['UserData'] = base64.b64encode(defn.config['userData'])

            if defn.config['instanceType']:
                args['LaunchTemplateData']['InstanceType'] = defn.config['instanceType']
            # if defn.config['securityGroupIds']!=[]:
                # args['LaunchTemplateData']['SecurityGroupIds'] = self.security_groups_to_ids(defn.config['subnetId'], defn.config['securityGroupIds'])
            if defn.config['placementGroup'] != "":
                args['LaunchTemplateData']['Placement']['GroupName'] = defn.config['placementGroup']
            if defn.config['zone']:
                args['LaunchTemplateData']['Placement']['AvailabilityZone'] = defn.config['zone']
            ######
            if defn.config['spotInstancePrice'] != 0:
                print 'here'
                args['LaunchTemplateData']['InstanceMarketOptions'] = dict(
                        MarketType="spot",
                        SpotOptions=dict(
                            MaxPrice=str(defn.config['spotInstancePrice']/100.0),
                            SpotInstanceType=defn.config['spotInstanceRequestType'],
                            ValidUntil=(datetime.datetime.utcnow() +
                                datetime.timedelta(0, defn.config['spotInstanceTimeout'])).isoformat(),
                            InstanceInterruptionBehavior=defn.config['spotInstanceInterruptionBehavior']
                        )
                    )
            if defn.config['subnetId'] == "" and defn.config['networkInterfaceId'] == "":
                raise Exception("You must specify either a subnetId or a networkInterfaceId")
            if defn.config['networkInterfaceId'] != "":
                args['LaunchTemplateData']['NetworkInterfaces'][0]['networkInterfaceId']=defn.config['networkInterfaceId']
            if defn.config['subnetId'] != "":
                args['LaunchTemplateData']['NetworkInterfaces'][0]['SubnetId']=defn.config['subnetId']
            if defn.config['secondaryPrivateIpAddressCount']:
                args['LaunchTemplateData']['NetworkInterfaces'][0]['SecondaryPrivateIpAddressCount']=defn.config['secondaryPrivateIpAddressCount']
            if defn.config['privateIpAddresses']:
                args['LaunchTemplateData']['NetworkInterfaces'][0]['PrivateIpAddresses']=defn.config['privateIpAddresses']
            if defn.config['keyPair'] != "":
                args['LaunchTemplateData']['KeyName']=defn.config['keyPair']

            ami = self._conn_boto3.describe_images(ImageIds=[defn.config['ami']])['Images'][0]

            # TODO: BlockDeviceMappings for non root volumes
            args['LaunchTemplateData']['BlockDeviceMappings'] = [dict(
                DeviceName="/dev/sda1",
                    Ebs=dict(
                        DeleteOnTermination=True,
                        VolumeSize=defn.config['ebsInitialRootDiskSize'],
                        VolumeType=ami['BlockDeviceMappings'][0]['Ebs']['VolumeType']
                    )
                )]
            # Use a client token to ensure that fleet creation is
            # idempotent; i.e., if we get interrupted before recording
            # the fleet ID, we'll get the same fleet ID on the
            # next run.
            if not self.clientToken:
                with self.depl._db:
                    self.clientToken = nixops.util.generate_random_string(length=48) # = 64 ASCII chars
                    self.state = self.STARTING

            args['ClientToken'] = self.clientToken
            self.log("creating launch template {} ...".format(defn.config['templateName']))
            try:
                launch_template = self._conn_boto3.create_launch_template(**args)
            except botocore.exceptions.ClientError as error:
                raise error
                # Not sure whether to use lambda retry or keep it like this
            with self.depl._db:
                self.templateId = launch_template['LaunchTemplate']['LaunchTemplateId']
                self.templateName = defn.config['templateName']
                self.templateVersion = defn.config['templateVersion']
                self.versionDescription = defn.config['versionDescription']
                self.state = self.UP
            # these are the tags for the template
            self._update_tag(defn)

    def check(self):

        self.connect_boto3(self.region)
        launch_template = self._conn_boto3.describe_launch_templates(
                    LaunchTemplateIds=[self.templateId]
                   )['LaunchTemplates']
        if launch_template is None:
            self.state = self.MISSING
            return
        if str(launch_template[0]['DefaultVersionNumber']) != self.templateVersion:
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