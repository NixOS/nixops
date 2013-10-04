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

    def __init__(self, xml):
        super(EC2SecurityGroupDefinition, self).__init__(xml)
        self.security_group_name = xml.find("attrs/attr[@name='name']/string").get("value")
        self.security_group_description = xml.find("attrs/attr[@name='description']/string").get("value")
        self.region = xml.find("attrs/attr[@name='region']/string").get("value")
        self.access_key_id = xml.find("attrs/attr[@name='accessKeyId']/string").get("value")
        self.rules = []
        for rule_xml in xml.findall("attrs/attr[@name='rules']/list/attrs"):
            ip_protocol = rule_xml.find("attrs/attr[@name='protocol']/string").get("value")
            if ip_protocol == "icmp":
                from_port = int(rule_xml.find("attrs/attr[@name='typeNumber']/int").get("value"))
                to_port = int(rule_xml.find("attrs/attr[@name='codeNumber']/int").get("value"))
            else:
                from_port = int(rule_xml.find("attrs/attr[@name='fromPort']/int").get("value"))
                to_port = int(rule_xml.find("attrs/attr[@name='toPort']/int").get("value"))
            cidr_ip_xml = rule_xml.find("attrs/attr[@name='sourceIp']/string")
            if not cidr_ip_xml is None:
                self.rules.append([ ip_protocol, from_port, to_port, cidr_ip_xml.get("value") ])
            else:
                group_name = rule_xml.find("attrs/attr[@name='sourceGroup']/attrs/attr[@name='groupName']/string").get("value")
                owner_id = rule_xml.find("attrs/attr[@name='sourceGroup']/attrs/attr[@name='ownerId']/string").get("value")
                self.rules.append([ ip_protocol, from_port, to_port, group_name, owner_id ])


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

    @classmethod
    def get_type(cls):
        return "ec2-security-group"

    def __init__(self, depl, name, id):
        super(EC2SecurityGroupState, self).__init__(depl, name, id)

    def show_type(self):
        s = super(EC2SecurityGroupState, self).show_type()
        if self.region: s = "{0} [{1}]".format(s, self.region)
        return s

    def prefix_definiton(self, attr):
        return {('resources', 'ec2SecurityGroups'): attr}

    def get_physical_spec(self):
        return {'groupId': self.security_group_id}

    @property
    def resource_id(self):
        return self.security_group_name

    def create_after(self, resources):
        #!!! TODO: Handle dependencies between security groups
        return {}

    def _connect(self):
        if self._conn: return
        self._conn = nixops.ec2_utils.connect(self.region, self.access_key_id)

    def create(self, defn, check, allow_reboot, allow_recreate):
        # Name or region change means a completely new security group
        if self.security_group_name and (defn.security_group_name != self.security_group_name or defn.region != self.region):
            with self.depl._db:
                self.state = self.UNKNOWN
                self.old_security_groups = self.old_security_groups + [{'name': self.security_group_name, 'region': self.region}]

        with self.depl._db:
            self.region = defn.region
            self.access_key_id = defn.access_key_id
            self.security_group_name = defn.security_group_name
            self.security_group_description = defn.security_group_description

        grp = None
        if check:
            with self.db:
                self._connect()

                try:
                    grp = self._conn.get_all_security_groups([ defn.security_group_name ])[0]
                    self.state = self.UP
                    self.security_group_id = grp.id
                    self.security_group_description = grp.description
                    rules = []
                    for rule in grp.rules:
                        for grant in rule.grants:
                            if grant.cidr_ip:
                                new_rule = [ rule.ip_protocol, rule.from_port, rule.to_port, grant.cidr_ip ]
                            else:
                                new_rule = [ rule.ip_protocol, rule.from_port, rule.to_port, grant.groupName, grant.owner_id ]
                            rules.append(new_rule)
                    self.security_group_rules = rules
                except boto.exception.EC2ResponseError as e:
                    if e.error_code == u'InvalidGroup.NotFound':
                        self.state = self.Missing
                    else:
                        raise

        new_rules = set()
        old_rules = set()
        for rule in self.security_group_rules:
            old_rules.add(tuple(rule))
        for rule in defn.security_group_rules:
            tupled_rule = tuple(rule)
            if not tupled_rule in old_rules:
                new_rules.add(tupled_rule)
            else:
                old_rules.remove(tupled_rule)

        if self.state == self.MISSING or self.state == self.UNKNOWN:
            self._connect()
            try:
                self.logger.log("creating EC2 security group `{0}'...".format(self.security_group_name))
                grp = self._conn.create_security_group(self.security_group_name, self.security_group_description)
                self.security_group_id = grp.id
            except boto.exception.EC2ResponseError as e:
                if self.state != self.UNKNOWN or e.error_code != u'InvalidGroup.Duplicate':
                    raise
            self.state = self.STARTING #ugh

        if new_rules:
            self.logger.log("adding new rules to EC2 security group `{0}'...".format(self.security_group_name))
            if grp is None:
                self._connect()
                grp = self._conn.get_all_security_groups([ self.security_group_name ])[0]
            for rule in new_rules:
                if len(rule) == 4:
                    grp.authorize(ip_protocol=rule[0], from_port=rule[1], to_port=rule[2], cidr_ip=rule[3])
                else:
                    src_group = boto.ec2.securitygroup.SecurityGroup(owner_id=rule[4], name=rule[3])
                    grp.authorize(ip_protocol=rule[0], from_port=rule[1], to_port=rule[2], src_group=src_group)

        if old_rules:
            self.logger.log("removing old rules from EC2 security group `{0}'...".format(self.security_group_name))
            if grp is None:
                self._connect()
                grp = self._conn.get_all_security_groups([ self.security_group_name ])[0]
            for rule in old_rules:
                if len(rule) == 4:
                    grp.revoke(ip_protocol=rule[0], from_port=rule[1], to_port=rule[2], cidr_ip=rule[3])
                else:
                    src_group = boto.ec2.securitygroup.SecurityGroup(owner_id=rule[4], name=rule[3])
                    grp.revoke(ip_protocol=rule[0], from_port=rule[1], to_port=rule[2], src_group=src_group)
        self.security_group_rules = defn.security_group_rules

        self.state = self.UP

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
            self.logger.log("deleting EC2 security group `{0}'...".format(self.security_group_name))
            self._connect()
            self._conn.delete_security_group(self.security_group_name)
            self.state = self.MISSING
        return True
