# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPC network interfaces attachement.

import time

import boto3
import botocore

import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
import nixops.ec2_utils
from nixops.diff import Diff, Handler
from nixops.state import StateDict

class VPCNetworkInterfaceAttachementDefinition(nixops.resources.ResourceDefinition):
    """Definition of a VPC network interface attachement"""

    @classmethod
    def get_type(cls):
        return "vpc-network-interface-attachement"

    @classmethod
    def get_resource_type(cls):
        return "vpcNetworkInterfaceAttachements"

    def show_type(self):
        return "{0}".format(self.get_type())

class VPCNetworkInterfaceAttachementState(nixops.resources.DiffEngineResourceState, EC2CommonState):
    """State of a VPC network interface attachement"""

    state = nixops.util.attr_property("state", nixops.resources.DiffEngineResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ['attachementId']

    @classmethod
    def get_type(cls):
        return "vpc-network-interface-attachement"

    def __init__(self, depl, name, id):
        nixops.resources.DiffEngineResourceState.__init__(self, depl, name, id)
        self._state = StateDict(depl, id)
        self.region = self._state.get('region', None)
        self.handle_create_eni_attachement = Handler(['region', 'networkInterfaceId', 'instanceId', 'deviceIndex' ],
                                          handle=self.realize_create_eni_attachement)

    def show_type(self):
        s = super(VPCNetworkInterfaceAttachementState, self).show_type()
        if self.region: s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return self._state.get('attachementId', None)

    def prefix_definition(self, attr):
        return {('resources', 'vpcNetworkInterfaceAttachements'): attr}

    def get_physical_spec(self):
        return { 'attachementId': self._state.get('attachementId', None) }

    def get_definition_prefix(self):
        return "resources.vpcNetworkInterfaceAttachements."

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc_network_interface.VPCNetworkInterfaceState) or
                isinstance(r, nixops.backends.ec2.EC2State)}

    def create(self, defn, check, allow_reboot, allow_recreate):
        diff_engine = self.setup_diff_engine(config=defn.config)
        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        for handler in diff_engine.plan():
            handler.handle(allow_recreate)

        self.ensure_state_up()

    def ensure_state_up(self):
        config = self.get_defn()
        self._state["region"] = config["region"]
        if self._state.get('attachementId', None):
            if self.state != self.UP:
                self.wait_for_eni_attachement(self._state['networkInterfaceId'])

    def wait_for_eni_attachement(self, eni_id):
        while True:
            response = self.get_client().describe_network_interface_attribute(
                Attribute='attachment',
                NetworkInterfaceId=eni_id)
            if response.get('Attachment', None):
                if response['Attachment']['Status'] == 'attached':
                    break
                elif response['Attachment']['Status'] != "attaching":
                    raise Exception("eni attachment {0} in an unexpected state {1}".format(
                        eni_id, response['Attachment']['Status']))
                self.log_continue(".")
                time.sleep(1)
            else:
                raise Exception("eni {} doesn't have any attachement {}".format(eni_id))

        self.log_end(" done")

        with self.depl._db:
            self.state = self.UP

    def realize_create_eni_attachement(self, allow_recreate):
        config = self.get_defn()
        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("network interface attachement {} definition changed and it needs to be recreated"
                                " use --allow-recreate if you want to create a new one".format(self._state['attachementId']))
            self.warn("network interface attachement definition changed, recreating ...")
            self._destroy()

        self._state['region'] = config['region']
        vm_id = config['instanceId']
        if vm_id.startswith("res-"):
            res = self.depl.get_typed_resource(vm_id[4:].split(".")[0], "ec2")
            vm_id = res.vm_id

        eni_id = config['networkInterfaceId']
        if eni_id.startswith("res-"):
            res = self.depl.get_typed_resource(eni_id[4:].split(".")[0], "vpc-network-interface")
            eni_id = res._state['networkInterfaceId']

        self.log("attaching network interface {0} to instance {1}".format(eni_id, vm_id))
        eni_attachement = self.get_client().attach_network_interface(
            DeviceIndex=config['deviceIndex'],
            InstanceId=vm_id,
            NetworkInterfaceId=eni_id)

        with self.depl._db:
            self.state = self.STARTING
            self._state['attachementId'] = eni_attachement['AttachmentId']
            self._state['instanceId'] = vm_id
            self._state['deviceIndex'] = config['deviceIndex']
            self._state['networkInterfaceId'] = eni_id

        self.wait_for_eni_attachement(eni_id)

    def wait_for_eni_detachment(self):
        self.log("waiting for eni attachement {0} to be detached from {1}".format(self._state['attachementId'], self._state["instanceId"]))
        while True:
            response = self.get_client().describe_network_interface_attribute(
                Attribute='attachment',
                NetworkInterfaceId=self._state['networkInterfaceId'])
            if response.get('Attachment', None):
                if response['Attachment']['Status'] == 'detached':
                    break
                elif response['Attachment']['Status'] != "detaching":
                    raise Exception("eni attachment {0} in an unexpected state {1}".format(
                        eni_id, response['Attachment']['Status']))
                self.log_continue(".")
                time.sleep(1)
            else:
                break

        self.log_end(" done")

    def _destroy(self):
        if self.state == self.UP:
            self.log("detaching vpc network interface attachement {}".format(self._state['attachementId']))
            try:
                self.get_client().detach_network_interface(AttachmentId=self._state['attachementId'],
                                                      Force=True)
                with self.depl._db:
                    self.state = self.STOPPING

            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] == "InvalidAttachmentID.NotFound":
                    self.warn("network interface attachement {} was already detached".format(self._state['attachementId']))
                else:
                    raise e
        if self.state == self.STOPPING:
            self.wait_for_eni_detachment()

        with self.depl._db:
            self.state = self.MISSING
            self._state['region'] = None
            self._state['attachementId'] = None
            self._state['instanceId'] = None
            self._state['deviceIndex'] = None
            self._state['networkInterfaceId'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
