# -*- coding: utf-8 -*-

from nixops.state import StateDict
from nixops.diff import Diff, Handler
import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
import nixops.ec2_utils

class AWSVPNGatewayDefinition(nixops.resources.ResourceDefinition):
    """Definition of an AWS VPN gateway."""

    @classmethod
    def get_type(cls):
        return "aws-vpn-gateway"

    @classmethod
    def get_resource_type(cls):
        return "awsVPNGateways"

    def show_type(self):
        return "{0}".format(self.get_type())

class AWSVPNGatewayState(nixops.resources.DiffEngineResourceState, EC2CommonState):
    """State of a AWS VPN gateway."""
    state = nixops.util.attr_property("state", nixops.resources.DiffEngineResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ["vpnGatewayId"]

    def __init__(self, depl, name, id):
        nixops.resources.DiffEngineResourceState.__init__(self, depl, name, id)
        self._state = StateDict(depl, id)
        self.handle_create_vpn_gtw = Handler(['region', 'zone', 'vpcId'], handle=self.realize_create_vpn_gtw)
        self.handle_tag_update = Handler(['tags'], after=[self.handle_create_vpn_gtw], handle=self.realize_update_tag)

    @classmethod
    def get_type(cls):
        return "aws-vpn-gateway"

    def show_type(self):
        s = super(AWSVPNGatewayState, self).show_type()
        if self._state.get('region', None): s = "{0} [{1}]".format(s, self._state['region'])
        return s

    @property
    def resource_id(self):
        return self._state.get('vpnGatewayId', None)

    def prefix_definition(self, attr):
        return {('resources', 'awsVPNGateways'): attr}

    def get_defintion_prefix(self):
        return "resources.awsVPNGateways."

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc.VPCState)}

    def realize_create_vpn_gtw(self, allow_recreate):
        config = self.get_defn()

        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("VPN gateway {} defintion changed"
                                " use --allow-recreate if you want to create a new one".format(
                                    self._state['vpnGatewayId']))
            self.warn("VPN gateway changed, recreating...")
            self._destroy()

        self._state['region'] = config['region']
        vpc_id = config['vpcId']
        if vpc_id.startswith("res-"):
            res = self.depl.get_typed_resource(vpc_id[4:].split(".")[0], "vpc")
            vpc_id = res._state['vpcId']

        self.log("creating VPN gateway in zone {}".format(config['zone']))
        response = self.get_client().create_vpn_gateway(
            AvailabilityZone=config['zone'],
            Type="ipsec.1")

        vpn_gtw_id = response['VpnGateway']['VpnGatewayId']
        self.log("attaching vpn gateway {0} to vpc {1}".format(vpn_gtw_id, vpc_id))
        self.get_client().attach_vpn_gateway(
            VpcId=vpc_id,
            VpnGatewayId=vpn_gtw_id)
        #TODO wait for the attchement state

        with self.depl._state.db:
            self.state = self.UP
            self._state['vpnGatewayId'] = vpn_gtw_id
            self._state['vpcId'] = vpc_id
            self._state['zone'] = config['zone']

    def realize_update_tag(self, allow_recreate):
        config = self.get_defn()
        tags = config['tags']
        tags.update(self.get_common_tags())
        self.get_client().create_tags(Resources=[self._state['vpnGatewayId']], Tags=[{"Key": k, "Value": tags[k]} for k in tags])

    def _destroy(self):
        if self.state != self.UP: return
        self.log("detaching vpn gateway {0} from vpc {1}".format(self._state['vpnGatewayId'], self._state['vpcId']))
        try:
            self.get_client().detach_vpn_gateway(
                VpcId=self._state['vpcId'],
                VpnGatewayId=self._state['vpnGatewayId'])
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == "InvalidVpnGatewayAttachment.NotFound":
                self.warn("VPN gateway '{0}' attachment with VPC '{1}' is invalid".format(
                    self._state['vpnGatewayId'], self._state['vpcId']))
            else:
                raise e

        # TODO delete VPN connections associated with this VPN gtw
        self.log("deleting vpn gateway {}".format(self._state['vpnGatewayId']))
        try:
            self.get_client().delete_vpn_gateway(
                VpnGatewayId=self._state['vpnGatewayId'])
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == "InvalidVpnGatewayID.NotFound":
                self.warn("VPN gateway {} was already deleted".format(self._state['vpnGatewayId']))
            else:
                raise e

        with self.depl._state.db:
            self.state = self.MISSING
            self._state['region'] = None
            self._state['vpnGatewayId'] = None
            self._state['vpcId'] = None
            self._state['zone'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
