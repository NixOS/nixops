# -*- coding: utf-8 -*-

# Automatic provisioning of EC2 security groups.
import boto3
import nixops.resources
import nixops.util
import nixops.ec2_utils
import botocore.exceptions

class EC2SecurityGroupDefinition(nixops.resources.ResourceDefinition):
    """Definition of an EC2 security group."""

    @classmethod
    def get_type(cls):
        return "ec2-security-group"

    @classmethod
    def get_resource_type(cls):
        return "ec2SecurityGroups"

    def __init__(self, xml):
        super(EC2SecurityGroupDefinition, self).__init__(xml)
        self.security_group_name = xml.find("attrs/attr[@name='name']/string").get("value")
        self.security_group_description = xml.find("attrs/attr[@name='description']/string").get("value")
        self.region = xml.find("attrs/attr[@name='region']/string").get("value")
        self.access_key_id = xml.find("attrs/attr[@name='accessKeyId']/string").get("value")

        self.vpc_id = None
        if not xml.find("attrs/attr[@name='vpcId']/string") is None:
            self.vpc_id = xml.find("attrs/attr[@name='vpcId']/string").get("value")

        self.security_group_rules = []
        for rule_xml in xml.findall("attrs/attr[@name='rules']/list/attrs"):
            ip_protocol = rule_xml.find("attr[@name='protocol']/string").get("value")
            if ip_protocol == "icmp":
                from_port = int(rule_xml.find("attr[@name='typeNumber']/int").get("value"))
                to_port = int(rule_xml.find("attr[@name='codeNumber']/int").get("value"))
            else:
                from_port = int(rule_xml.find("attr[@name='fromPort']/int").get("value"))
                to_port = int(rule_xml.find("attr[@name='toPort']/int").get("value"))
            cidr_ip_xml = rule_xml.find("attr[@name='sourceIp']/string")
            if not cidr_ip_xml is None:
                self.security_group_rules.append([ ip_protocol, from_port, to_port, cidr_ip_xml.get("value") ])
            else:
                group_name = rule_xml.find("attr[@name='sourceGroup']/attrs/attr[@name='groupName']/string").get("value")
                owner_id = rule_xml.find("attr[@name='sourceGroup']/attrs/attr[@name='ownerId']/string").get("value")
                self.security_group_rules.append([ ip_protocol, from_port, to_port, group_name, owner_id ])

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region)

class EC2SecurityGroupState(nixops.resources.ResourceState):
    """State of an EC2 security group."""

    region = nixops.util.attr_property("ec2.region", None)
    security_group_id = nixops.util.attr_property("ec2.securityGroupId", None)
    security_group_name = nixops.util.attr_property("ec2.securityGroupName", None)
    security_group_description = nixops.util.attr_property("ec2.securityGroupDescription", None)
    security_group_rules = nixops.util.attr_property("ec2.securityGroupRules", [], 'json')
    old_security_groups = nixops.util.attr_property("ec2.oldSecurityGroups", [], 'json')
    vpc_id = nixops.util.attr_property("ec2.vpcId", None)
    access_key_id = nixops.util.attr_property("ec2.accessKeyId", None)


    @classmethod
    def get_type(cls):
        return "ec2-security-group"

    def __init__(self, depl, name, id):
        super(EC2SecurityGroupState, self).__init__(depl, name, id)
        self._conn_boto3 = None


    def show_type(self):
        s = super(EC2SecurityGroupState, self).show_type()
        if self.region: s = "{0} [{1}]".format(s, self.region)
        return s

    def prefix_definition(self, attr):
        return {('resources', 'ec2SecurityGroups'): attr}

    def get_physical_spec(self):
        return {'groupId': self.security_group_id}

    @property
    def resource_id(self):
        return self.security_group_name

    def create_after(self, resources, defn):
        #!!! TODO: Handle dependencies between security groups
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc.VPCState) or
                isinstance(r, nixops.resources.elastic_ip.ElasticIPState)
               }

    def connect_boto3(self):
        if self._conn_boto3: return self._conn_boto3
        self._conn_boto3 = nixops.ec2_utils.connect_ec2_boto3(self.region, self.access_key_id)
        return self._conn_boto3

    def process_rule(self, config):
        args = dict()

        # An error occurs when providing both GroupName and GroupId
        #args['GroupName'] = self.security_group_name
        args['GroupId'] = self.security_group_id
        args['FromPort'] = config.get('FromPort', None)
        args['IpProtocol'] = config.get('IpProtocol', None)
        args['ToPort'] = config.get('ToPort', None)
        if config['IpRanges'] != []:
            args['CidrIp'] = config['IpRanges'][0].get('CidrIp', None)
        else:
            args['SourceSecurityGroupName'] = config['UserIdGroupPairs'][0].get('GroupId', None)
            args['SourceSecurityGroupOwnerId'] = config['UserIdGroupPairs'][0].get('UserId', None)
        return {attr : args[attr] for attr in args if args[attr] is not None}

    def create(self, defn, check, allow_reboot, allow_recreate):
        def retry_notfound(f):
            nixops.ec2_utils.retry(f, error_codes=['InvalidGroup.NotFound'])

        #Name or region change means a completely new security group
        #import sys; import pdb; pdb.Pdb(stdout=sys.__stdout__).set_trace()
        if self.security_group_name and (defn.security_group_name != self.security_group_name or defn.region != self.region):
            with self.depl._db:
                self.state = self.UNKNOWN
                self.old_security_groups = self.old_security_groups + [{'name': self.security_group_name, 'region': self.region}]

        if defn.vpc_id is not None:
            if defn.vpc_id.startswith("res-"):
                res = self.depl.get_typed_resource(defn.vpc_id[4:].split(".")[0], "vpc")
                defn.vpc_id = res._state['vpcId']

        with self.depl._db:
            self.region = defn.region
            self.access_key_id = defn.access_key_id or nixops.ec2_utils.get_access_key_id()
            self.security_group_name = defn.security_group_name
            self.security_group_description = defn.security_group_description
            self.vpc_id = defn.vpc_id

        def generate_rule(rule):
            return {
                'FromPort': rule.get('FromPort', None),
                'IpRanges': rule.get('IpRanges', []),
                'ToPort': rule.get('ToPort', None),
                'IpProtocol': rule.get('IpProtocol', None),
                'UserIdGroupPairs': rule.get('UserIdGroupPairs', []),
            }
        def evolve_rule(rule):

            if len(rule) == 4:
                return {
                    'FromPort': rule[1],
                    'IpRanges': [{'CidrIp': rule[3]}],
                    'ToPort': rule[2],
                    'IpProtocol': rule[0],
                    'UserIdGroupPairs': []
                }
            else:
                return {
                    'FromPort': rule[1],
                    'IpRanges': [],
                    'ToPort': rule[2],
                    'IpProtocol': rule[0],
                    'UserIdGroupPairs': [{'UserId': rule[4], 'GroupId': rule[3]}]
                }

        if check and self.state != self.UNKNOWN:
            with self.depl._db:

                self.connect_boto3()

                try:
                    grp = self.get_security_group()
                except botocore.exceptions.ClientError as error:
                    if error.grp['Error']['Code'] == 'InvalidGroup.NotFound':
                        self.warn("EC2 security group {} not found, performing destroy to sync the state ...".format(self.security_group_name))
                        self.destroy()
                        return
                    else:
                        raise error
                rules = []
                for rule in grp['SecurityGroups'][0].get('IpPermissions', []):
                    rules.append(generate_rule(rule))
                self.security_group_rules = rules

        # Dereference elastic IP if used for the source ip
        resolved_security_group_rules = []
        for rule in defn.security_group_rules:
            if rule[-1].startswith("res-"):
                res = self.depl.get_typed_resource(rule[-1][4:], "elastic-ip")
                rule[-1] = res.public_ipv4 + '/32'
            resolved_security_group_rules.append(evolve_rule(rule))

        rules_to_remove = [r for r in self.security_group_rules if r not in resolved_security_group_rules ]
        rules_to_add = [r for r in resolved_security_group_rules if r not in self.security_group_rules ]

        if self.state == self.MISSING or self.state == self.UNKNOWN:
            self.connect_boto3()
            try:
                self.logger.log("creating EC2 security group ‘{0}’...".format(self.security_group_name))
                grp = self._conn_boto3.create_security_group(Description=self.security_group_description, GroupName=self.security_group_name, VpcId=defn.vpc_id)
                self.security_group_id = grp['GroupId']
            except botocore.exceptions.ClientError as e:
                if self.state != self.UNKNOWN or e.response['Error']['Code'] != 'InvalidGroup.Duplicate':
                    raise

            self.state = self.STARTING #ugh

        self.connect_boto3()
        if rules_to_remove:

            self.log("removing old rules from EC2 security group ‘{0}’...".format(self.security_group_name))
            for rule in rules_to_remove:
                kwargs = self.process_rule(rule)
                self._conn_boto3.revoke_security_group_ingress(**kwargs)

        if rules_to_add:
            try:
                self.log("adding new rules to EC2 security group ‘{0}’...".format(self.security_group_name))
                for rule in rules_to_add:
                    kwargs = self.process_rule(rule)
                    self._conn_boto3.authorize_security_group_ingress(**kwargs)
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] != 'InvalidPermission.Duplicate':
                    raise

        self.security_group_rules = resolved_security_group_rules
        self.state = self.UP

    def get_security_group(self):
        if self.vpc_id:
            return self._conn_boto3.describe_security_groups(GroupIds=[ self.security_group_id ])
        else:
            return self._conn_boto3.describe_security_groups(GroupNames=[ self.security_group_name ])

    def after_activation(self, defn):
        region = self.region
        self.connect_boto3()
        conn = self._conn_boto3
        for group in self.old_security_groups:
            if group['region'] != region:
                region = group['region']
                conn = nixops.ec2_utils.connect_ec2_boto3(region, self.access_key_id)
            try:
                conn.delete_security_group(GroupId=self.security_group_id)
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] != 'InvalidGroup.NotFound':
                    raise
        self.old_security_groups = []

    def destroy(self, wipe=False):
        if self.state == self.UP or self.state == self.STARTING:
            self.logger.log("deleting EC2 security group: `{0}' ID `{1}'...".format(
                self.security_group_name, self.security_group_id))
            self.connect_boto3()

            try:
                nixops.ec2_utils.retry(
                    lambda: self._conn_boto3.delete_security_group(GroupId=self.security_group_id),
                    error_codes=['DependencyViolation'])
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] != 'InvalidGroup.NotFound':
                    raise
                else:
                    self.logger.log(e.response['Error']['Message'])

            self.state = self.MISSING
        return True
