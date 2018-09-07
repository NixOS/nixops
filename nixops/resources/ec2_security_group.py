# -*- coding: utf-8 -*-

# Automatic provisioning of EC2 security groups.

import boto.ec2.securitygroup
import nixops.resources
import nixops.util
import nixops.ec2_utils

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
    access_key_id = nixops.util.attr_property("ec2.accessKeyId", None)
    vpc_id = nixops.util.attr_property("ec2.vpcId", None)

    @classmethod
    def get_type(cls):
        return "ec2-security-group"

    def __init__(self, depl, name, id):
        super(EC2SecurityGroupState, self).__init__(depl, name, id)
        self._conn = None

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

    def _connect(self):
        if self._conn: return
        self._conn = nixops.ec2_utils.connect(self.region, self.access_key_id)

    def create(self, defn, check, allow_reboot, allow_recreate):
        def retry_notfound(f):
            nixops.ec2_utils.retry(f, error_codes=['InvalidGroup.NotFound'])

        # Name or region change means a completely new security group
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

        grp = None
        if check:
            with self.depl._db:
                self._connect()

                try:
                    if self.vpc_id:
                        grp = self._conn.get_all_security_groups(group_ids=[ self.security_group_id ])[0]
                    else:
                        grp = self._conn.get_all_security_groups([ defn.security_group_name ])[0]
                    self.state = self.UP
                    self.security_group_id = grp.id
                    self.security_group_description = grp.description
                    rules = []
                    for rule in grp.rules:
                        for grant in rule.grants:
                            new_rule = [ rule.ip_protocol, int(rule.from_port), int(rule.to_port) ]
                            if grant.cidr_ip:
                                new_rule.append(grant.cidr_ip)
                            else:
                                group  = nixops.ec2_utils.id_to_security_group_name(self._conn, grant.groupId, self.vpc_id) if self.vpc_id else grant.groupName
                                new_rule.append(group)
                                new_rule.append(grant.owner_id)
                            rules.append(new_rule)
                    self.security_group_rules = rules
                except boto.exception.EC2ResponseError as e:
                    if e.error_code == u'InvalidGroup.NotFound':
                        self.state = self.MISSING
                    else:
                        raise

        # Dereference elastic IP if used for the source ip
        resolved_security_group_rules = []
        for rule in defn.security_group_rules:
            if rule[-1].startswith("res-"):
                res = self.depl.get_typed_resource(rule[-1][4:], "elastic-ip")
                rule[-1] = res.public_ipv4 + '/32'
            resolved_security_group_rules.append(rule)

        new_rules = set()
        old_rules = set()
        for rule in self.security_group_rules:
            old_rules.add(tuple(rule))
        for rule in resolved_security_group_rules:
            tupled_rule = tuple(rule)
            if not tupled_rule in old_rules:
                new_rules.add(tupled_rule)
            else:
                old_rules.remove(tupled_rule)

        if self.state == self.MISSING or self.state == self.UNKNOWN:
            self._connect()
            try:
                self.logger.log("creating EC2 security group ‘{0}’...".format(self.security_group_name))
                grp = self._conn.create_security_group(self.security_group_name, self.security_group_description, defn.vpc_id)
                self.security_group_id = grp.id
            except boto.exception.EC2ResponseError as e:
                if self.state != self.UNKNOWN or e.error_code != u'InvalidGroup.Duplicate':
                    raise
            self.state = self.STARTING #ugh

        if new_rules:
            self.logger.log("adding new rules to EC2 security group ‘{0}’...".format(self.security_group_name))
            if grp is None:
                self._connect()
                grp = self.get_security_group()
            for rule in new_rules:
                try:
                    if len(rule) == 4:
                        retry_notfound(lambda: grp.authorize(ip_protocol=rule[0], from_port=rule[1], to_port=rule[2], cidr_ip=rule[3]))
                    else:
                        args = {}
                        args['owner_id']=rule[4]
                        if self.vpc_id:
                            args['id']=nixops.ec2_utils.name_to_security_group(self._conn, rule[3], self.vpc_id)
                        else:
                            args['name']=rule[3]
                        src_group = boto.ec2.securitygroup.SecurityGroup(**args)
                        retry_notfound(lambda: grp.authorize(ip_protocol=rule[0], from_port=rule[1], to_port=rule[2], src_group=src_group))
                except boto.exception.EC2ResponseError as e:
                    if e.error_code != u'InvalidPermission.Duplicate':
                        raise

        if old_rules:
            self.logger.log("removing old rules from EC2 security group ‘{0}’...".format(self.security_group_name))
            if grp is None:
                self._connect()
                grp = self.get_security_group()
            for rule in old_rules:
                if len(rule) == 4:
                    grp.revoke(ip_protocol=rule[0], from_port=rule[1], to_port=rule[2], cidr_ip=rule[3])
                else:
                    args = {}
                    args['owner_id']=rule[4]
                    if self.vpc_id:
                        args['id']=nixops.ec2_utils.name_to_security_group(self._conn, rule[3], self.vpc_id)
                    else:
                        args['name']=rule[3]
                    src_group = boto.ec2.securitygroup.SecurityGroup(**args)
                    grp.revoke(ip_protocol=rule[0], from_port=rule[1], to_port=rule[2], src_group=src_group)
        self.security_group_rules = resolved_security_group_rules

        self.state = self.UP

    def get_security_group(self):
        if self.vpc_id:
            return self._conn.get_all_security_groups(group_ids=[ self.security_group_id ])[0]
        else:
            return self._conn.get_all_security_groups(groupnames=[ self.security_group_name ])[0]

    def after_activation(self, defn):
        region = self.region
        self._connect()
        conn = self._conn
        for group in self.old_security_groups:
            if group['region'] != region:
                region = group['region']
                conn = nixops.ec2_utils.connect(region, self.access_key_id)
            try:
                conn.delete_security_group(group['name'])
            except boto.exception.EC2ResponseError as e:
                if e.error_code != u'InvalidGroup.NotFound':
                    raise
        self.old_security_groups = []

    def destroy(self, wipe=False):
        if self.state == self.UP or self.state == self.STARTING:
            self.logger.log("deleting EC2 security group `{0}' ID `{1}'...".format(
                self.security_group_name, self.security_group_id))
            self._connect()
            try:
                nixops.ec2_utils.retry(
                    lambda: self._conn.delete_security_group(group_id=self.security_group_id),
                    error_codes=['DependencyViolation'])
            except boto.exception.EC2ResponseError as e:
                if e.error_code != u'InvalidGroup.NotFound':
                    raise

            self.state = self.MISSING
        return True
