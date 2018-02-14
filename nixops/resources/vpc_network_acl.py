# -*- coding: utf-8 -*-

# automatic provisioning of aws vpc network ACLs.

import boto3
import botocore
import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
import nixops.ec2_utils
from nixops.diff import Diff, Handler
from nixops.state.state_helper import StateDict

class VPCNetworkAcldefinition(nixops.resources.ResourceDefinition):
    """definition of a vpc network ACL."""

    @classmethod
    def get_type(cls):
        return "vpc-network-acl"

    @classmethod
    def get_resource_type(cls):
        return "vpcNetworkAcls"

    def show_type(self):
        return "{0}".format(self.get_type())


class VPCNetworkAclstate(nixops.resources.DiffEngineResourceState, EC2CommonState):
    """state of a vpc Network ACL."""

    state = nixops.util.attr_property("state", nixops.resources.DiffEngineResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ['networkAclId']

    @classmethod
    def get_type(cls):
        return "vpc-network-acl"

    def __init__(self, depl, name, id):
        nixops.resources.DiffEngineResourceState.__init__(self, depl, name, id)
        self._state = StateDict(depl, id)
        self.network_acl_id = self._state.get('networkAclId', None)
        self.handle_create_network_acl = Handler(['region', 'vpcId'], handle=self.realize_create_network_acl)
        self.handle_entries = Handler(['entries'], after=[self.handle_create_network_acl]
                                      , handle=self.realize_entries_change)
        self.handle_subnet_association = Handler(['subnetIds'], after=[self.handle_create_network_acl]
                                                 , handle=self.realize_subnets_change)
        self.handle_tag_update = Handler(['tags'], after=[self.handle_create_network_acl], handle=self.realize_update_tag)

    def show_type(self):
        s = super(VPCNetworkAclstate, self).show_type()
        if self._state.get('region', None): s = "{0} [{1}]".format(s, self._state['region'])
        return s

    @property
    def resource_id(self):
        return self.network_acl_id

    def prefix_definition(self, attr):
        return {('resources', 'vpcNetworkAcls'): attr}

    def get_definition_prefix(self):
        return "resources.vpcNetworkAcls."

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc.VPCState) or
                isinstance(r, nixops.resources.vpc_subnet.VPCSubnetState)}

    def realize_create_network_acl(self, allow_recreate):
        config = self.get_defn()
        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("network ACL {} definition changed and it needs to be recreated"
                                " use --allow-recreate if you want to create a new one".format(self.network_acl_id))
            self.warn("network ACL definition changed, recreating ...")
            self._destroy()

        self._state['region'] = config['region']

        vpc_id = config['vpcId']

        if vpc_id.startswith("res-"):
            res = self.depl.get_typed_resource(vpc_id[4:].split(".")[0], "vpc")
            vpc_id = res._state['vpcId']

        self.log("creating network ACL in vpc {}".format(vpc_id))
        response = self.get_client().create_network_acl(VpcId=vpc_id)
        self.network_acl_id = response['NetworkAcl']['NetworkAclId']

        with self.depl._state.db:
            self.state = self.UP
            self._state['vpcId'] = vpc_id
            self._state['networkAclId'] = self.network_acl_id

    def realize_entries_change(self, allow_recreate):
        config = self.get_defn()
        old_entries = self._state.get('entries', [])
        new_entries = config['entries']
        to_remove = [e for e in old_entries if e not in new_entries]
        to_create = [e for e in new_entries if e not in old_entries]
        for entry in to_remove:
            try:
                self.get_client().delete_network_acl_entry(NetworkAclId=self.network_acl_id, RuleNumber=entry['ruleNumber'], Egress=entry['egress'])
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] == "InvalidNetworkAclEntry.NotFound":
                    self.warn("rule {0} was already deleted from network ACL {1}".format(entry['ruleNumber'], self.network_acl_id))
                else:
                    raise e

        for entry in to_create:
            rule = self.process_rule_entry(entry)
            self.get_client().create_network_acl_entry(**rule)
        with self.depl._state.db:
            self._state['entries'] = config['entries']

    def realize_subnets_change(self, allow_recreate):
        config = self.get_defn()
        old_subnets = self._state.get('subnetIds', [])
        new_subnets = []
        for s in config['subnetIds']:
            if s.startswith("res-"):
                res = self.depl.get_typed_resource(s[4:].split(".")[0], "vpc-subnet")
                new_subnets.append(res._state['subnetId'])
            else:
                new_subnets.append(s)

        vpc_id = config['vpcId']

        if vpc_id.startswith("res-"):
            res = self.depl.get_typed_resource(vpc_id[4:].split(".")[0], "vpc")
            vpc_id = res._state['vpcId']

        subnets_to_remove = [s for s in old_subnets if s not in new_subnets]
        subnets_to_add = [s for s in new_subnets if s not in old_subnets]

        default_network_acl = self.get_default_network_acl(vpc_id)

        for subnet in subnets_to_remove:
            association_id = self.get_network_acl_association(subnet)
            self.log("associating subnet {0} to default network acl {1}".format(subnet, default_network_acl))
            self.get_client().replace_network_acl_association(AssociationId=association_id, NetworkAclId=default_network_acl)

        for subnet in subnets_to_add:
            association_id = self.get_network_acl_association(subnet)
            self.log("associating subnet {0} to network acl {1}".format(subnet, self.network_acl_id))
            self.get_client().replace_network_acl_association(AssociationId=association_id, NetworkAclId=self.network_acl_id)

        with self.depl._state.db:
            self._state['subnetIds'] = new_subnets

    def get_default_network_acl(self, vpc_id):
        response = self.get_client().describe_network_acls(Filters=[{ "Name": "default", "Values": [ "true" ] },
             { "Name": "vpc-id", "Values": [ vpc_id ]}])
        return response['NetworkAcls'][0]['NetworkAclId']

    def get_network_acl_association(self, subnet_id):
        response = self.get_client().describe_network_acls(Filters=[{"Name": "association.subnet-id", "Values":[ subnet_id ]}])
        for association in  response['NetworkAcls'][0]['Associations']:
            if association['SubnetId'] == subnet_id:
                return association['NetworkAclAssociationId']

    def process_rule_entry(self, entry):
        rule = dict()
        rule['NetworkAclId'] = self.network_acl_id
        rule['Protocol'] = entry['protocol']
        rule['RuleNumber'] = entry['ruleNumber']
        rule['RuleAction'] = entry['ruleAction']
        rule['Egress'] = entry['egress']
        if entry['cidrBlock'] is not None: rule['CidrBlock'] = entry['cidrBlock']
        if entry['ipv6CidrBlock'] is not None: rule['Ipv6CidrBlock'] = entry['ipv6CidrBlock']
        if entry['icmpCode'] and entry['icmpType']:
            rule['IcmpTypeCode'] = {"Type": entry['icmpType'], "Code": entry['icmpCode']}
        if entry['fromPort'] and entry['toPort']:
            rule['PortRange'] = { "From": entry['fromPort'], "To": entry['toPort'] }
        return rule

    def _destroy(self):
        if self.state != self.UP: return
        try:
            subnets = self._state.get('subnetIds', [])
            default_network_acl = self.get_default_network_acl(self._state['vpcId'])
            for subnet in subnets:
                association_id = self.get_network_acl_association(subnet)
                self.log("associating subnet {0} to default network acl {1}".format(subnet, default_network_acl))
                self.get_client().replace_network_acl_association(AssociationId=association_id, NetworkAclId=default_network_acl)
            self.log("deleting network acl {}".format(self.network_acl_id))
            self.get_client().delete_network_acl(NetworkAclId=self.network_acl_id)
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'InvalidNetworkAclID.NotFound':
                self.warn("network ACL {} was already deleted".format(self.network_acl_id))
            else:
                raise e

        with self.depl._state.db:
            self.state = self.MISSING
            self._state['networkAclId'] = None
            self._state['region'] = None
            self._state['vpcId'] = None
            self._state['entries'] = None

    def realize_update_tag(self, allow_recreate):
        config = self.get_defn()
        tags = config['tags']
        tags.update(self.get_common_tags())
        self.get_client().create_tags(Resources=[self._state['networkAclId']], Tags=[{"Key": k, "Value": tags[k]} for k in tags])

    def destroy(self, wipe=False):
        self._destroy()
        return True
