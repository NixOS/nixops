# -*- coding: utf-8 -*-

# Automatic provisioning of AWS Route53 Hosted Zones.

import os
import time
import botocore
import boto3
import uuid
import nixops.util
import nixops.resources
import nixops.ec2_utils
from pprint import pprint

#boto3.set_stream_logger(name='botocore')

class Route53HostedZoneDefinition(nixops.resources.ResourceDefinition):
    """Definition of an Route53 Hosted Zone."""

    @classmethod
    def get_type(cls):
        return "aws-route53-hosted-zone"

    @classmethod
    def get_resource_type(cls):
        return "route53HostedZones"

    def __init__(self, xml, config):
        nixops.resources.ResourceDefinition.__init__(self, xml, config)
        self.access_key_id = config["accessKeyId"]
        self.comment = config["comment"]
        self.private_zone =  config["privateZone"]
        self.zone_name = config['name']
        self.associated_vpcs = config['associatedVPCs']
        map(lambda x: x.pop('_module'), self.associated_vpcs)


class Route53HostedZoneState(nixops.resources.ResourceState):
    """State of a Route53 Hosted Zone."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("ec2.accessKeyId", None)
    zone_id = nixops.util.attr_property("route53.zoneId", None)
    zone_name = nixops.util.attr_property("route53.zoneName", None)
    private_zone = nixops.util.attr_property("route53.privateZone", False)
    comment = nixops.util.attr_property('route53.comment', None)
    delegation_set = nixops.util.attr_property('route53.delegationSet', [], 'json')

    @classmethod
    def get_type(cls):
        return "aws-route53-hosted-zone"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._boto_session = None

    @property
    def resource_id(self):
        return self.zone_id

    def prefix_definition(self, attr):
        return {('resources', 'route53HostedZones'): attr}

    def get_physical_spec(self):
        return { 'delegationSet': self.delegation_set}

    def boto_session(self):
        if self._boto_session is None:
            (access_key_id, secret_access_key) = nixops.ec2_utils.fetch_aws_secret_key(self.access_key_id)
            self._boto_session = boto3.session.Session(
                                               aws_access_key_id=access_key_id,
                                               aws_secret_access_key=secret_access_key)
        return self._boto_session

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.access_key_id = defn.access_key_id or nixops.ec2_utils.get_access_key_id()
        if not (self.access_key_id or os.environ['AWS_ACCESS_KEY_ID']):
            raise Exception("please set ‘accessKeyId’ or $AWS_ACCESS_KEY_ID")

        client = self.boto_session().client("route53")

        hosted_zone = None
        if self.zone_id:
            hosted_zone = client.get_hosted_zone(Id=self.zone_id)

        if not hosted_zone:
            args = {}
            args['Name'] = defn.zone_name
            args['CallerReference'] = str(uuid.uuid4())
            args['HostedZoneConfig'] = { 'PrivateZone': defn.private_zone }

            if defn.private_zone:
                first_assoc = defn.associated_vpcs[0]
                args['VPC'] = { 'VPCRegion': first_assoc['region'], 'VPCId': first_assoc['vpcId'] }

            self.log('creating hosted zone for {}'.format(defn.zone_name))

            hosted_zone = client.create_hosted_zone(**args)
            with self.depl._db:
                self.state = self.UP
                self.zone_id = hosted_zone['HostedZone']['Id']
                self.private_zone = defn.private_zone
                self.zone_name = defn.zone_name
                self.comment = defn.comment
                self.delegation_set = hosted_zone['DelegationSet']['NameServers']

        if defn.comment != self.comment or check:
            client.update_hosted_zone_comment(Id=self.zone_id, Comment=defn.comment)

        # associate VPC's
        if self.private_zone:
            current = [ { 'region': assoc['VPCRegion'], 'vpcId': assoc['VPCId']} for assoc in hosted_zone['VPCs']]
            tbd = [ assoc for assoc in current if not assoc in defn.associated_vpcs ]
            tba = [ assoc for assoc in defn.associated_vpcs if not assoc in current]

            for assoc in tba:
                client.associate_vpc_with_hosted_zone(HostedZoneId=self.zone_id, VPC={ 'VPCId': assoc['vpcId'], 'VPCRegion': assoc['region'] })

            for assoc in tbd:
                client.disassociate_vpc_from_hosted_zone(HostedZoneId=self.zone_id, VPC={ 'VPCId': assoc['vpcId'], 'VPCRegion': assoc['region'] })

        with self.depl._db:
            self.associated_vpcs = defn.associated_vpcs

        return True

    def destroy(self, wipe=False):
        client = self.boto_session().client("route53")

        if not self.zone_id: return

        self.log('destroying hosted zone for {}'.format(self.zone_name))
        try:
            client.delete_hosted_zone(Id=self.zone_id)
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchHostedZone':
                pass

        with self.depl._db:
            self.state = self.MISSING
            self.zone_id = None
            self.zone_name = None
            self.private_zone = None
            self.comment = None
            self.delegation_set = None

