# -*- coding: utf-8 -*-
import datetime
import time
import sys
import nixops.util
import nixops.resources
import botocore.exceptions
from nixops.resources.ec2_common import EC2CommonState

class ec2FleetDefinition(nixops.resources.ResourceDefinition):
    """Definition of an ec2 fleet"""

    @classmethod
    def get_type(cls):
        return "ec2-fleet"

    @classmethod
    def get_resource_type(cls):
        return "ec2Fleet"

    def show_type(self):
        return "{0}".format(self.get_type())


class ec2FleetState(nixops.resources.ResourceState, EC2CommonState):
    """State of an ec2 fleet"""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    region = nixops.util.attr_property("region", None)
    excessCapacityTerminationPolicy = nixops.util.attr_property("ExcessCapacityTerminationPolicy", None)
    launchTemplateVersion = nixops.util.attr_property("launchTemplateVersion", None)
    launchTemplateOverrides = nixops.util.attr_property("launchTemplateOverrides", {}, 'json')
    launchTemplateName = nixops.util.attr_property("launchTemplateName", None)
    terminateInstancesWithExpiration = nixops.util.attr_property("TerminateInstancesWithExpiration", True, type=bool)
    fleetRequestType = nixops.util.attr_property("fleetRequestType", None)
    replaceUnhealthyInstances = nixops.util.attr_property("replaceUnhealthyInstances", False, type=bool)
    spotAllocationStrategy = nixops.util.attr_property("spotAllocationStrategy", None)
    spotInstanceInterruptionBehavior = nixops.util.attr_property("spotInstanceInterruptionBehavior", None)
    spotInstancePoolsToUseCount = nixops.util.attr_property("spotInstancePoolsToUseCount", None)
    spotSingleInstanceType = nixops.util.attr_property("spotSingleInstanceType", True, type=bool)
    spotSingleAvailabilityZone = nixops.util.attr_property("spotSingleAvailabilityZone", True, type=bool)
    spotMinTargetCapacity = nixops.util.attr_property("spotMinTargetCapacity", None, int)
    onDemandAllocationStrategy = nixops.util.attr_property("onDemandAllocationStrategy", None)
    onDemandSingleInstanceType = nixops.util.attr_property("onDemandSingleInstanceType", True, type=bool)
    onDemandSingleAvailabilityZone = nixops.util.attr_property("onDemandSingleAvailabilityZone", True, type=bool)
    onDemandMinTargetCapacity = nixops.util.attr_property("onDemandMinTargetCapacity", None, int)
    totalTargetCapacity = nixops.util.attr_property("totalTargetCapacity", None, int)
    onDemandTargetCapacity = nixops.util.attr_property("onDemandTargetCapacity", None, int)
    spotTargetCapacity = nixops.util.attr_property("spotTargetCapacity", None, int)
    defaultTargetCapacityType = nixops.util.attr_property("defaultTargetCapacityType", None)
    terminateInstancesOnDeletion = nixops.util.attr_property("terminateInstancesOnDeletion", False, type=bool)
    client_token = nixops.util.attr_property("fleetClientToken", None)
    fleetId = nixops.util.attr_property("fleetId", None)
    fleetInstances = nixops.util.attr_property("fleetInstances", {}, 'json')

    @classmethod
    def get_type(cls):
        return "ec2-fleet"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._conn_boto3 = None

    def _exists(self):
        return self.state != self.MISSING

    def show_type(self):
        s = super(ec2FleetState, self).show_type()
        return s

    @property
    def resource_id(self):
        return self.fleetId

    def connect_boto3(self, region):
        if self._conn_boto3: return self._conn_boto3
        self._conn_boto3 = nixops.ec2_utils.connect_ec2_boto3(region, self.access_key_id)
        return self._conn_boto3

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.ec2_launch_template.ec2LaunchTemplateState)}

    def _update_tag(self, defn):
        self.connect_boto3(self.region)
        tags = defn.config['tags']
        tags.update(self.get_common_tags())
        self._conn_boto3.create_tags(Resources=[self.fleetId], Tags=[{"Key": k, "Value": tags[k]} for k in tags])

    def create(self, defn, check, allow_reboot, allow_recreate):

        if self.region is None:
            self.region = defn.config['region']
        elif self.region != defn.config['region']:
            self.warn("cannot change region of a running instance (from ‘{}‘ to ‘{}‘)".format(self.region, defn.config['region']))

        self.terminateInstancesOnDeletion = defn.config['terminateInstancesOnDeletion']
        self.access_key_id = defn.config['accessKeyId']
        self.connect_boto3(self.region)

        # check if the desired capacity changed then update it.
        if self.state == self.UP and (self.totalTargetCapacity != defn.config['targetCapacitySpecification']['totalTargetCapacity'] or
            self.onDemandTargetCapacity != defn.config['targetCapacitySpecification']['onDemandTargetCapacity'] or
            self.spotTargetCapacity != defn.config['targetCapacitySpecification']['spotTargetCapacity'] or
            self.defaultTargetCapacityType != defn.config['targetCapacitySpecification']['defaultTargetCapacityType'] or
            self.excessCapacityTerminationPolicy != defn.config['excessCapacityTerminationPolicy']):
            check = True
            args = dict(
                ExcessCapacityTerminationPolicy=defn.config['excessCapacityTerminationPolicy'],
                FleetId=self.fleetId,
                TargetCapacitySpecification=dict(
                    TotalTargetCapacity=defn.config['targetCapacitySpecification']['totalTargetCapacity']
                    #TODO: Currently ec2-fleet only support total target capacity modification.
                    #TODO: Uncomment below when changing that become supported
                    # OnDemandTargetCapacity=defn.config['targetCapacitySpecification']['onDemandTargetCapacity'],
                    # SpotTargetCapacity=defn.config['targetCapacitySpecification']['spotTargetCapacity'],
                    # DefaultTargetCapacityType=defn.config['targetCapacitySpecification']['defaultTargetCapacityType']
                )
            )
            try:
                self._conn_boto3.modify_fleet(**args)
            except botocore.exceptions.ClientError as error:
                raise error

            with self.depl._db:
                self.totalTargetCapacity = defn.config['targetCapacitySpecification']['totalTargetCapacity']
                self.onDemandTargetCapacity = defn.config['targetCapacitySpecification']['onDemandTargetCapacity']
                self.spotTargetCapacity = defn.config['targetCapacitySpecification']['spotTargetCapacity']
                self.defaultTargetCapacityType = defn.config['targetCapacitySpecification']['defaultTargetCapacityType']
                self.excessCapacityTerminationPolicy = defn.config['excessCapacityTerminationPolicy']

        # Create the fleet dict request.
        if self.state != self.UP:
            args = dict()
            if defn.config['spotOptions']['minTargetCapacity']:
                args['SpotOptions'] = dict(
                    AllocationStrategy=defn.config['spotOptions']['allocationStrategy'],
                    InstanceInterruptionBehavior=defn.config['spotOptions']['instanceInterruptionBehavior'],
                    SingleInstanceType=defn.config['spotOptions']['singleInstanceType'],
                    SingleAvailabilityZone=defn.config['spotOptions']['singleAvailabilityZone'],
                    MinTargetCapacity=defn.config['spotOptions']['minTargetCapacity']
                )
                if defn.config['spotOptions']['allocationStrategy'] == "lowestPrice":
                    if defn.config['spotOptions']['instancePoolsToUseCount']:
                        args['SpotOptions']['InstancePoolsToUseCount']=defn.config['spotOptions']['instancePoolsToUseCount']
                        self.spotInstancePoolsToUseCount = defn.config['spotOptions']['instancePoolsToUseCount']
                with self.depl._db:
                    self.spotAllocationStrategy = defn.config['spotOptions']['allocationStrategy']
                    self.spotInstanceInterruptionBehavior = defn.config['spotOptions']['instanceInterruptionBehavior']
                    self.spotSingleInstanceType = defn.config['spotOptions']['singleInstanceType']
                    self.spotSingleAvailabilityZone = defn.config['spotOptions']['singleAvailabilityZone']
                    self.spotMinTargetCapacity = defn.config['spotOptions']['minTargetCapacity']
            if defn.config['onDemandOptions']['minTargetCapacity']:
                args['OnDemandOptions'] = dict(
                    AllocationStrategy=defn.config['onDemandOptions']['allocationStrategy'],
                    SingleInstanceType=defn.config['onDemandOptions']['singleInstanceType'],
                    SingleAvailabilityZone=defn.config['onDemandOptions']['singleAvailabilityZone'],
                    MinTargetCapacity=defn.config['onDemandOptions']['minTargetCapacity']
                )
                with self.depl._db:
                    self.onDemandAllocationStrategy = defn.config['onDemandOptions']['allocationStrategy']
                    self.onDemandSingleInstanceType = defn.config['onDemandOptions']['singleInstanceType']
                    self.onDemandSingleAvailabilityZone = defn.config['onDemandOptions']['singleAvailabilityZone']
                    self.onDemandMinTargetCapacity = defn.config['onDemandOptions']['minTargetCapacity']
            args['TargetCapacitySpecification'] = dict(
                TotalTargetCapacity=defn.config['targetCapacitySpecification']['totalTargetCapacity'],
                OnDemandTargetCapacity=defn.config['targetCapacitySpecification']['onDemandTargetCapacity'],
                SpotTargetCapacity=defn.config['targetCapacitySpecification']['spotTargetCapacity'],
                DefaultTargetCapacityType=defn.config['targetCapacitySpecification']['defaultTargetCapacityType']
            )
            with self.depl._db:
                self.totalTargetCapacity = defn.config['targetCapacitySpecification']['totalTargetCapacity']
                self.onDemandTargetCapacity = defn.config['targetCapacitySpecification']['onDemandTargetCapacity']
                self.spotTargetCapacity = defn.config['targetCapacitySpecification']['spotTargetCapacity']
                self.defaultTargetCapacityType = defn.config['targetCapacitySpecification']['defaultTargetCapacityType']

            args['ExcessCapacityTerminationPolicy'] = defn.config['excessCapacityTerminationPolicy']
            if defn.config['launchTemplateVersion'].startswith("res-"):
                res = self.depl.get_typed_resource(defn.config['launchTemplateVersion'][4:].split(".")[0], "ec2-launch-template")
                defn.config['launchTemplateVersion'] = res.templateVersion
            args['LaunchTemplateConfigs'] = [dict(
                LaunchTemplateSpecification=dict(
                    LaunchTemplateName=defn.config['launchTemplateName'],
                    Version=defn.config['launchTemplateVersion']
                ),
                Overrides=defn.config['launchTemplateOverrides']
            )]

            args['TerminateInstancesWithExpiration'] = defn.config['terminateInstancesWithExpiration']
            args['Type'] = defn.config['fleetRequestType']

            if defn.config['ec2FleetValidFrom']:
                args['ValidFrom'] = (datetime.datetime.utcnow() +
                        datetime.timedelta(0, defn.config['ec2FleetValidFrom'])).isoformat()
            if defn.config['ec2FleetValidUntil']:
                args['validUntil'] = (datetime.datetime.utcnow() +
                        datetime.timedelta(0, defn.config['ec2FleetValidUntil'])).isoformat()

            args['ReplaceUnhealthyInstances'] = defn.config['replaceUnhealthyInstances']
            # TODO: work on tags
            # for instances you need to specify that in the launch template
            # make sure to use tag updater to put the default nixops tags in here
            # args['TagSpecifications'] = [dict(
            #     ResourceType='fleet',
            #     Tags = [defn.config['tags']]
            # )]

            # Use a client token to ensure that fleet creation is
            # idempotent; i.e., if we get interrupted before recording
            # the fleet ID, we'll get the same fleet ID on the
            # next run.
            if not self.client_token:
                with self.depl._db:
                    self.client_token = nixops.util.generate_random_string(length=48) # = 64 ASCII chars
                    #self.state = self.STARTING

            args['ClientToken'] = self.client_token

            # fleet = self._retry(
            #     lambda: self._conn_boto3.create_fleet(**args)
            # )

            try:
                fleet = self._conn_boto3.create_fleet(**args)
            except botocore.exceptions.ClientError as error:
                raise error
                #TODO: handle IdempotentParameterMismatch
                # Not sure whether to use lambda retry or keep it like this
            with self.depl._db:
                self.state = self.STARTING
                self.fleetId = fleet['FleetId']
                self.excessCapacityTerminationPolicy = defn.config['excessCapacityTerminationPolicy']
                self.launchTemplateVersion = defn.config['launchTemplateVersion']
                self.launchTemplateOverrides = defn.config['launchTemplateOverrides']
                self.launchTemplateName = defn.config['launchTemplateName']
                self.terminateInstancesWithExpiration = defn.config['terminateInstancesWithExpiration']
                self.fleetRequestType = defn.config['fleetRequestType']
                self.replaceUnhealthyInstances = defn.config['replaceUnhealthyInstances']

            self.log_start("deploying EC2 fleet... ".format(self.name))
            fleetState = self._conn_boto3.describe_fleets(
                        FleetIds=[self.fleetId]
                       )['Fleets'][0]['FleetState']
            while True:
                self.log_continue("[{}] ".format(fleetState))
                if fleetState == "active": break
                time.sleep(3)
                fleetState = self._conn_boto3.describe_fleets(FleetIds=[self.fleetId])['Fleets'][0]['FleetState']
            self.log_end("")

        if self.state == self.STARTING or check:
            self.log_start("EC2 fleet activity status... ".format(self.name))
            fleetStatus = self._conn_boto3.describe_fleets(
                        FleetIds=[self.fleetId]
                       )['Fleets'][0]['ActivityStatus']
            while True:
                self.log_continue("[{}] ".format(fleetStatus))
                if fleetStatus == "error":
                    raise Exception("ec2 fleet activity status is error; check your config")
                    # i need to fix this bette way
                if fleetStatus == "fulfilled": break
                time.sleep(3)
                fleetStatus = self._conn_boto3.describe_fleets(FleetIds=[self.fleetId])['Fleets'][0]['ActivityStatus']
            self.log_end("")
            self._update_tag(defn)
            self._get_fleet_instances()
            self.state = self.UP

    def check(self):
        self.connect_boto3(self.region)
        if self.fleetId is None:
            self.state = self.MISSING
            return []
        fleet = self._conn_boto3.describe_fleets(
                    FleetIds=[self.fleetId]
                   )['Fleets']
        if fleet is None:
            self.state = self.MISSING
            return []
            # check with amine if we should set the other stuff to None
        # getting the instances IDs
        self._get_fleet_instances()
        instances_status = self.get_instances_status()
        return instances_status

    def _get_active_fleet_instance(self):
        self.connect_boto3(self.region)
        return self._conn_boto3.describe_fleet_instances(FleetId=self.fleetId)['ActiveInstances']

    def _get_fleet_instances(self):
        self.connect_boto3(self.region)
        fleet_instances = []
        activeInstances = self._get_active_fleet_instance()
        for i in activeInstances:
            instance = self._conn_boto3.describe_instances(InstanceIds=[i['InstanceId']])['Reservations'][0]['Instances'][0]
            fleet_instance = dict(
                instanceId=i['InstanceId'],
                instanceType=i['InstanceType'],
                ami=instance['ImageId'],
                keyPair = instance.get('KeyName', None),
                ebsOptimized=instance['EbsOptimized'],
                placement=dict(
                    zone=instance['Placement']['AvailabilityZone'],
                    tenancy=instance['Placement']['Tenancy']
                ),
                securityGroupIds=instance['NetworkInterfaces'][0]['Groups'][0]['GroupId'],
                subnetId=instance['SubnetId'],
            )
            if 'PublicIpAddress' in instance.keys():
                fleet_instance['publicIpAddress'] = instance['PublicIpAddress']
            if 'IamInstanceProfile' in instance.keys():
                fleet_instance['instanceProfile'] = instance['IamInstanceProfile']['Arn']
            if 'SpotInstanceRequestId' in i.keys():
                fleet_instance['SpotInstanceRequestId'] = i['SpotInstanceRequestId']
            fleet_instances.append(fleet_instance)
        if self.fleetInstances is not None and self.fleetInstances != fleet_instances:
            self.warn("EC2 fleet instances configration changed")
            self.fleetInstances = fleet_instances

    def get_instances_status(self):
        self.connect_boto3(self.region)
        instance_status = []
        activeInstances = self._get_active_fleet_instance()
        for i in activeInstances:
            instance = self._conn_boto3.describe_instance_status(InstanceIds=[i['InstanceId']])['InstanceStatuses'][0]
            if instance['InstanceStatus']['Details'][0]['Status'] == "passed" and instance['SystemStatus']['Details'][0]['Status'] == "passed":
                s_check = "2/2"
            elif instance['InstanceStatus']['Details'][0]['Status'] == "passed" and instance['SystemStatus']['Details'][0]['Status'] == "failed":
                s_check = "1/2"
            elif instance['InstanceStatus']['Details'][0]['Status'] == "failed" and instance['SystemStatus']['Details'][0]['Status'] == "failed":
                s_check = "0/2"
            else:
                s_check = "Insufficient Data"
            i_s = dict(
                instanceId=instance['InstanceId'],
                instanceState=instance['InstanceState']['Name'],
                statusCheck=s_check
            )
            if "Events" in instance.keys():
                i_s['event']=instance['Events'][0]['Code']
            else:
                i_s['event'] = " "
            for j in self.fleetInstances:
                if j['instanceId'] == instance['InstanceId']:
                    if 'publicIpAddress' in j.keys():
                        i_s['publicIpAddress']=j['publicIpAddress']
                    else:
                        i_s['publicIpAddress'] = "No Public IP for this instance"
            instance_status.append(i_s)
        return instance_status

    def _destroy(self):
        self.connect_boto3(self.region)
        if self.terminateInstancesOnDeletion:
            self.warn("terminateInstancesOnDeletion is set to {}, hence all instance related to the Fleet will be terminated ..."
                        .format(self.terminateInstancesOnDeletion))

        self.log_start("destroying EC2 fleet... ".format(self.name))
        fleet = self._conn_boto3.describe_fleets(
                    FleetIds=[self.fleetId])['Fleets']
        if fleet:
            self._conn_boto3.delete_fleets(
                        FleetIds=[self.fleetId],
                        TerminateInstances=self.terminateInstancesOnDeletion)
            while True:
                FleetState = self._conn_boto3.describe_fleets(FleetIds=[self.fleetId])['Fleets'][0]['FleetState']
                if self.terminateInstancesOnDeletion:
                    fleetInstances = self._conn_boto3.describe_fleet_instances(FleetId=self.fleetId)
                    instances = [i['InstanceId'] for i in fleetInstances['ActiveInstances']]
                    while True:
                        if instances == []:
                            break
                        else:
                            self.log_continue("destroying ({0} left) ... ".format(len(instances)))
                            time.sleep(2)
                            fleetInstances = self._conn_boto3.describe_fleet_instances(FleetId=self.fleetId)
                            instances = [i['InstanceId'] for i in fleetInstances['ActiveInstances']]
                self.log_continue("[{0}] ".format(FleetState))
                if FleetState == "terminated" or FleetState == "deleted": break
                time.sleep(4)
        self.log_end("")

    def destroy(self, wipe=False):
        if not self._exists(): return True

        self._destroy()
        return True