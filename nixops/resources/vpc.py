# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPCs.

import boto3
import botocore

import nixops.util
import nixops.resources
import nixops.resources.ec2_common
import nixops.ec2_utils
from nixops.state import StateDict
from nixops.diff import Diff, Handler

class VPCDefinition(nixops.resources.ResourceDefinition):
    """Definition of a VPC."""

    @classmethod
    def get_type(cls):
        return "vpc"

    @classmethod
    def get_resource_type(cls):
        return "vpc"

    def show_type(self):
        return "{0}".format(self.get_type())


class VPCState(nixops.resources.ResourceState, nixops.resources.ec2_common.EC2CommonState):
    """State of a VPC."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)

    @classmethod
    def get_type(cls):
        return "vpc"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._client = None
        self._state = StateDict(depl, id)
        self._config = None
        self.vpc_id = self._state.get('vpcId', None)
        # declare the different handlers
        self.handle_create = Handler(['cidrBlock', 'region', 'instanceTenancy'])
        self.handle_create.handle = self.handle_create_vpc
        self.handle_dns = Handler(['enableDnsHostnames', 'enableDnsSupport'], after=[self.handle_create])
        self.handle_dns.handle = self.handle_dns_config
        self.handle_classic_link = Handler(['enableClassicLink'], after=[self.handle_create])
        self.handle_classic_link.handle = self.handle_classic_link_change

    def get_handlers(self):
        return [getattr(self,h) for h in dir(self) if isinstance(getattr(self,h), Handler)]

    def show_type(self):
        s = super(VPCState, self).show_type()
        region = self._state.get('region', None)
        if region: s = "{0} [{1}]".format(s, region)
        return s

    @property
    def resource_id(self):
        return self._state.get('vpcId', None)

    def prefix_definition(self, attr):
        return {('resources', 'vpc'): attr}

    def get_physical_spec(self):
        return { 'vpcId': self._state.get('vpcId', None)}

    def get_definition_prefix(self):
        return "resources.vpc."

    def connect(self):
        if self._client: return
        assert self._state['region']
        (access_key_id, secret_access_key) = nixops.ec2_utils.fetch_aws_secret_key(self.access_key_id)
        self._client = boto3.client('ec2', region_name=self._state['region'], aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)

    def _destroy(self):
        if self.state != self.UP: return
        self.connect()
        self.log("destroying vpc {0}...".format(self._state['vpcId']))
        try:
            self._client.delete_vpc(VpcId=self._state['vpcId'])
        except botocore.exceptions.ClientError as e:
            if e.response ['Error']['Code'] == 'InvalidVpcID.NotFound':
                self.warn("vpc {0} was already deleted".format(self._state['vpcId']))
            else:
                raise e

        with self.depl._db:
            self.state = self.MISSING
            self._state['vpcId'] = None
            self._state['region'] = None
            self._state['cidrBlock'] = None
            self._state['instanceTenancy'] = None
            self._state['enableDnsSupport'] = None
            self._state['enableDnsHostname'] = None
            self._state['enableVpcClassicLink'] = None

    def create(self, defn, check, allow_reboot, allow_recreate):
        # diff engine setup
        self._config = defn.config
        self.allow_recreate = allow_recreate
        diff_engine = Diff(depl=self.depl, logger=self.logger, config=defn.config,
                state=self._state, res_type=self.get_type())
        diff_engine.set_reserved_keys(['vpcId', 'accessKeyId', 'tags', 'ec2.tags'])
        diff_engine.set_handlers(self.get_handlers())
        change_sequence = diff_engine.plan()

        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        self._state["region"] = defn.config['region']

        # handle vpcs that are deleted from outside nixops e.g console
        existant=True
        if self._state.get('vpcId', None):
            try:
                self.connect()
                self._client.describe_vpcs(VpcIds=[ self._state["vpcId"] ])
            except botocore.exceptions.ClientError as e:
                if e.response ['Error']['Code'] == 'InvalidVpcID.NotFound':
                    self.warn("vpc {0} was deleted from outside nixops, it will be recreated...".format(self._state["vpcId"]))
                    existant=False
                else:
                    raise e

        if not existant:
            self.allow_recreate = True
            self.handle_create_vpc()

        for handler in change_sequence:
            handler.handle()

        def tag_updater(tags):
            self._client.create_tags(Resources=[ self.vpc_id ], Tags=[{"Key": k, "Value": tags[k]} for k in tags])

        self.update_tags_using(tag_updater, user_tags=defn.config["tags"], check=check)

        with self.depl._db:
           self.state = self.UP
           self._state["vpcId"] = self.vpc_id
           self._state["region"] = defn.config['region']
           self._state["cidrBlock"] = defn.config['cidrBlock']
           self._state["instanceTenancy"] = defn.config['instanceTenancy']
           self._state["enableDnsSupport"] = defn.config['enableDnsSupport']
           self._state["enableDnsHostnames"] = defn.config['enableDnsHostnames']
           self._state["enableClassicLink"] = defn.config['enableClassicLink']

    def handle_create_vpc(self):
        """Handle both create and recreate of the vpc resource """
        if self.state == self.UP:
            if not self.allow_recreate:
               raise Exception("vpc {} definition changed and it needs to be recreated "
                               "use --allow-recreate if you want to create a new one".format(self.vpc_id))
            self.warn("vpc definition changed, recreating...")
            self._destroy()
            self._client = None
            self._state["region"] = self._config['region']

        self.connect()
        self.log("creating vpc under region {0}".format(self._config['region']))
        vpc = self._client.create_vpc(CidrBlock=self._config['cidrBlock'], InstanceTenancy=self._config['instanceTenancy'])
        self.vpc_id = vpc.get('Vpc').get('VpcId')

        with self.depl._db:
           self.state = self.UP
           self._state["vpcId"] = self.vpc_id
           self._state["region"] = self._config['region']
           self._state["cidrBlock"] = self._config['cidrBlock']
           self._state["instanceTenancy"] = self._config['instanceTenancy']

    def handle_classic_link_change(self):
        self.connect()
        if self._config['enableClassicLink']:
            self._client.enable_vpc_classic_link(VpcId=self.vpc_id)
        else:
            self._client.disable_vpc_classic_link(VpcId=self.vpc_id)
        with self.depl._db:
            self._state["enableClassicLink"] = self._config['enableClassicLink']

    def handle_dns_config(self):
        self.connect()
        self._client.modify_vpc_attribute(VpcId=self.vpc_id, EnableDnsSupport={ 'Value': self._config['enableDnsSupport'] })
        self._client.modify_vpc_attribute(VpcId=self.vpc_id, EnableDnsHostnames={ 'Value': self._config['enableDnsHostnames'] })

    def destroy(self, wipe=False):
        self._destroy()
        return True
