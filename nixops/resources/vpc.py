# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPCs.

import boto3
import botocore

import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
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


class VPCState(nixops.resources.ResourceState, EC2CommonState):
    """State of a VPC."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ["vpcId"]

    @classmethod
    def get_type(cls):
        return "vpc"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._client = None
        self._state = StateDict(depl, id)
        self.vpc_id = self._state.get('vpcId', None)
        self.handle_create = Handler(['cidrBlock', 'region', 'instanceTenancy'], handle=self.realize_create_vpc)
        self.handle_dns = Handler(['enableDnsHostnames', 'enableDnsSupport'], after=[self.handle_create]
                                  , handle=self.realize_dns_config)
        self.handle_classic_link = Handler(['enableClassicLink'], after=[self.handle_create]
                                           , handle=self.realize_classic_link_change)

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
        self._client = boto3.session.Session().client('ec2', region_name=self._state['region'], aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)

    def _destroy(self):
        if self.state != self.UP: return
        self.connect()
        self.log("destroying vpc {0}...".format(self._state['vpcId']))
        try:
            self._client.delete_vpc(VpcId=self._state['vpcId'])
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'InvalidVpcID.NotFound':
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

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.elastic_ip.ElasticIPState)}

    def create(self, defn, check, allow_reboot, allow_recreate):
        diff_engine = self.setup_diff_engine(config=defn.config)

        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        for handler in diff_engine.plan():
            handler.handle(allow_recreate)

        self.ensure_state_up(check)

    def ensure_state_up(self, check):
        config = self.get_defn()
        self._state["region"] = config['region']
        self.connect()
        # handle vpcs that are deleted from outside nixops e.g console
        if self._state.get('vpcId', None):
            if check:
                try:
                    self._client.describe_vpcs(VpcIds=[self._state["vpcId"]])
                except botocore.exceptions.ClientError as e:
                    if e.response['Error']['Code'] == 'InvalidVpcID.NotFound':
                        self.warn("vpc {0} was deleted from outside nixops,"
                                  " it will be recreated...".format(self._state["vpcId"]))
                        allow_recreate = True
                        self.realize_create_vpc(allow_recreate)
                        self.realize_classic_link_change(allow_recreate)
                        self.realize_dns_config(allow_recreate)
                    else:
                        raise e
            if self.state != self.UP:
                self.wait_for_vpc_available(self._state['vpcId'])

    def wait_for_vpc_available(self, vpc_id):
        while True:
            response = self._client.describe_vpcs(VpcIds=[vpc_id])
            if len(response['Vpcs']) == 1:
                vpc = response['Vpcs'][0]
                if vpc['State'] == "available":
                    break
                elif vpc['State'] != "pending":
                    raise Exception("vpc {0} is in an unexpected state {1}".format(
                        vpc_id, vpc['State']))

                self.log_continue(".")
                time.sleep(1)
            else:
                raise Exception("couldn't find vpc {}, please run a deploy with --check")
        self.log_end(" done")

        with self.depl._db:
            self.state = self.UP

    def realize_create_vpc(self, allow_recreate):
        """Handle both create and recreate of the vpc resource """
        config = self.get_defn()
        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("vpc {} definition changed and it needs to be recreated "
                                "use --allow-recreate if you want to create a new one".format(self.vpc_id))
            self.warn("vpc definition changed, recreating...")
            self._destroy()
            self._client = None

        self._state["region"] = config['region']

        self.connect()
        self.log("creating vpc under region {0}".format(config['region']))
        vpc = self._client.create_vpc(CidrBlock=config['cidrBlock'],
                                      InstanceTenancy=config['instanceTenancy'])
        self.vpc_id = vpc.get('Vpc').get('VpcId')

        with self.depl._db:
            self.state = self.STARTING
            self._state["vpcId"] = self.vpc_id
            self._state["region"] = config['region']
            self._state["cidrBlock"] = config['cidrBlock']
            self._state["instanceTenancy"] = config['instanceTenancy']

        def tag_updater(tags):
            self._client.create_tags(Resources=[self.vpc_id], Tags=[{"Key": k, "Value": tags[k]} for k in tags])

        self.update_tags_using(tag_updater, user_tags=config["tags"], check=True)

        self.wait_for_vpc_available(self.vpc_id)

    def realize_classic_link_change(self, allow_recreate):
        config = self.get_defn()
        self.connect()
        if config['enableClassicLink']:
            self._client.enable_vpc_classic_link(VpcId=self.vpc_id)
        else:
            self._client.disable_vpc_classic_link(VpcId=self.vpc_id)
        with self.depl._db:
            self._state["enableClassicLink"] = config['enableClassicLink']

    def realize_dns_config(self, allow_recreate):
        config = self.get_defn()
        self.connect()
        self._client.modify_vpc_attribute(VpcId=self.vpc_id,
                                          EnableDnsSupport={
                                              'Value': config['enableDnsSupport']
                                              })
        self._client.modify_vpc_attribute(VpcId=self.vpc_id,
                                          EnableDnsHostnames={
                                              'Value': config['enableDnsHostnames']
                                              })
        with self.depl._db:
            self._state["enableDnsSupport"] = config['enableDnsSupport']
            self._state["enableDnsHostnames"] = config['enableDnsHostnames']

    def destroy(self, wipe=False):
        self._destroy()
        return True
