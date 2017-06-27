# -*- coding: utf-8 -*-

# automatic provisioning of aws vpc network ACLs.

import boto3
import botocore
import nixops.util
import nixops.resources
import nixops.resources.ec2_common
import nixops.ec2_utils
from nixops.diff import Diff, Handler
from nixops.state import StateDict

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


class VPCNetworkAclstate(nixops.resources.ResourceState, nixops.resources.ec2_common.EC2CommonState):
    """state of a vpc Network ACL."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)

    @classmethod
    def get_type(cls):
        return "vpc-network-acl"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._client = None
        self._state = StateDict(depl, id)
        self._config = None
        self.network_acl_id = self._state.get('networkAclId', None)
        self.handle_create_network_acl = Handler(['region', 'vpcId'])
        self.handle_entries = Handler(['entries'], after=[self.handle_create_network_acl])
        self.handle_subnet_association = Handler(['subnetIds'], after=[self.handle_create_network_acl])
        self.handle_create_network_acl.handle = self.realize_create_network_acl
        self.handle_entries.handle = self.realize_entries_change
        self.handle_subnet_association.handle = self.realize_subnets_change

    def get_handlers(self):
        return [getattr(self,h) for h in dir(self) if isinstance(getattr(self,h), Handler)]

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

    def connect(self):
        if self._client: return
        assert self._state['region']
        (access_key_id, secret_access_key) = nixops.ec2_utils.fetch_aws_secret_key(self.access_key_id)
        self._client = boto3.client('ec2', region_name=self._state['region'], aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc.VPCState)}

    def create(self, defn, check, allow_reboot, allow_recreate):
        self._config = defn.config
        self.allow_recreate = allow_recreate
        diff_engine = Diff(depl=self.depl, logger=self.logger, config=defn.config,
                state=self._state, res_type=self.get_type())
        diff_engine.set_reserved_keys(['networkAclId', 'accessKeyId', 'tags', 'ec2.tags'])
        diff_engine.set_handlers(self.get_handlers())
        change_sequence = diff_engine.plan()

        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        for h in change_sequence:
            h.handle()

    def realize_create_network_acl(self):
        if self.state == self.UP:
            if not self.allow_recreate:
                raise Exception("network ACL {} definition changed and it needs to be recreated"
                                " use --allow-recreate if you want to create a new one".format(self.network_acl_id))
            self.warn("network ACL definition changed, recreating ...")
            self._destroy()
            self._client = None

        self._state['region'] = self._config['region']
        self.connect()

        vpc_id = self._config['vpcId']

        if vpc_id.startswith("res-"):
            res = self.depl.get_typed_resource(vpc_id[4:].split(".")[0], "vpc")
            vpc_id = res._state['vpcId']

        self.log("creating network ACL in vpc {}".format(vpc_id))
        response = self._client.create_network_acl(VpcId=vpc_id)
        self.network_acl_id = response['NetworkAcl']['NetworkAclId']

        with self.depl._db:
            self.state = self.UP
            self._state['vpcId'] = vpc_id
            self._state['networkAclId'] = self.network_acl_id

    def realize_entries_change(self):
        self.connect()
        old_entries = self._state.get('entries', [])
        new_entries = self._config['entries']
        to_remove = [e for e in old_entries if e not in new_entries]
        to_create = [e for e in new_entries if e not in old_entries]
        for entry in to_remove:
            try:
                self._client.delete_network_acl_entry(NetworkAclId=self.network_acl_id, RuleNumber=entry['ruleNumber'], Egress=entry['egress'])
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] == "InvalidNetworkAclEntry.NotFound":
                    self.warn("rule {0} was already deleted from network ACL {1}".format(entry['ruleNumber'], self.network_acl_id))
                else:
                    raise e

        for entry in to_create:
            rule = self.process_rule_entry(entry)
            self._client.create_network_acl_entry(**rule)
        with self.depl._db:
            self._state['entries'] = self._config['entries']

    def realize_subnets_change(self):
        self.connect()
        old_subnets = self._state.get('subnetIds', [])
        new_subnets = []
        for s in self._config['subnetIds']:
            if s.startswith("res-"):
                res = self.depl.get_typed_resource(s[4:].split(".")[0], "vpc-subnet")
                new_subnets.append(res._state['subnetId'])
            else:
                new_subnets.append(s)

        subnets_to_remove = [s for s in old_subnets if s not in new_subnets]
        subnets_to_add = [s for s in new_subnets if s not in old_subnets]

        default_network_acl = self.get_default_network_acl(self._config['vpcId'])

        for subnet in subnets_to_remove:
            association_id = self.get_network_acl_association(subnet)
            self.log("associating subnet {0} to default network acl {1}".format(subnet, default_network_acl))
            self._client.replace_network_acl_association(AssociationId=association_id, NetworkAclId=default_network_acl)

        for subnet in subnets_to_add:
            association_id = self.get_network_acl_association(subnet)
            self.log("associating subnet {0} to default network acl {1}".format(subnet, self.network_acl_id))
            self._client.replace_network_acl_association(AssociationId=association_id, NetworkAclId=self.network_acl_id)

        with self.depl._db:
            self._state['subnetIds'] = new_subnets

    def get_default_network_acl(self, vpc_id):
        response = self._client.describe_network_acls(Filters=[{ "Name": "default", "Values": [ "true" ] },
             { "Name": "vpc-id", "Values": [ vpc_id ]}])
        return response['NetworkAcls'][0]['NetworkAclId']

    def get_network_acl_association(self, subnet_id):
        response = self._client.describe_network_acls(Filters=[{"Name": "association.subnet-id", "Values":[ subnet_id ]}])
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
        rule['CidrBlock'] = entry['cidrBlock']
        if entry['icmpCode'] and entry['icmpType']:
            rule['IcmpTypeCode'] = {"Type": entry['icmpType'], "Code": entry['icmpCode']}
        if entry['fromPort'] and entry['toPort']:
            rule['PortRange'] = { "From": entry['fromPort'], "To": entry['toPort'] }
        return rule

    def _destroy(self):
        if self.state != self.UP: return
        self.log("deleting network acl {}".format(self.network_acl_id))
        self.connect()
        try:
            self._client.delete_network_acl(NetworkAclId=self.network_acl_id)
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'InvalidNetworkAclID.NotFound':
                self.warn("network ACL {} was already deleted".format(self.network_acl_id))
            else:
                raise e

        with self.depl._db:
            self.state = self.MISSING
            self._state['networkAclId'] = None
            self._state['region'] = None
            self._state['vpcId'] = None
            self._state['entries'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
