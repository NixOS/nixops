# -*- coding: utf-8 -*-

# Automatic provisioning of EC2 placement groups

import boto.ec2.placementgroup
import nixops.resources
import nixops.util
import nixops.ec2_utils

class EC2PlacementGroupDefinition(nixops.resources.ResourceDefinition):
    """Definition of an EC2 placement group."""

    @classmethod
    def get_type(cls):
        return "ec2-placement-group"

    @classmethod
    def get_resource_type(cls):
        return "ec2PlacementGroups"

    def __init__(self, xml):
        super(EC2PlacementGroupDefinition, self).__init__(xml)
        self.placement_group_name = xml.find("attrs/attr[@name='name']/string").get("value")
        self.placement_group_strategy = xml.find("attrs/attr[@name='strategy']/string").get("value")
        self.region = xml.find("attrs/attr[@name='region']/string").get("value")
        self.access_key_id = xml.find("attrs/attr[@name='accessKeyId']/string").get("value")

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region)

class EC2PlacementGroupState(nixops.resources.ResourceState):
    """State of an EC2 placement group."""

    region = nixops.util.attr_property("ec2.region", None)
    placement_group_name = nixops.util.attr_property("ec2.placementGroupName", None)
    placement_group_strategy = nixops.util.attr_property("ec2.placementGroupStrategy", None)
    old_placement_groups = nixops.util.attr_property("ec2.oldPlacementGroups", [], 'json')
    access_key_id = nixops.util.attr_property("ec2.accessKeyId", None)

    @classmethod
    def get_type(cls):
        return "ec2-placement-group"

    def __init__(self, depl, name, id):
        super(EC2PlacementGroupState, self).__init__(depl, name, id)
        self._conn = None

    def show_type(self):
        s = super(EC2PlacementGroupState, self).show_type()
        if self.region: s = "{0} [{1}]".format(s, self.region)
        return s

    def prefix_definition(self, attr):
        return {('resources', 'ec2PlacementGroups'): attr}

    def get_physical_spec(self):
        return {}

    @property
    def resource_id(self):
        return self.placement_group_name

    def _connect(self):
        if self._conn: return
        self._conn = nixops.ec2_utils.connect(self.region, self.access_key_id)

    def create(self, defn, check, allow_reboot, allow_recreate):
        # Name or region change means a completely new security group
        if self.placement_group_name and (defn.placement_group_name != self.placement_group_name or defn.region != self.region):
            with self.depl._state.db:
                self.state = self.UNKNOWN
                self.old_placement_groups = self.old_placement_groups + [{'name': self.placement_group_name, 'region': self.region}]

        with self.depl._state.db:
            self.region = defn.region
            self.access_key_id = defn.access_key_id or nixops.ec2_utils.get_access_key_id()
            self.placement_group_name = defn.placement_group_name
            self.placement_group_strategy = defn.placement_group_strategy

        grp = None
        if check:
            with self.depl._state.db:
                self._connect()

                try:
                    grp = self._conn.get_all_placement_groups([ defn.placement_group_name ])[0]
                    self.state = self.UP
                    self.placement_group_strategy = grp.strategy
                except boto.exception.EC2ResponseError as e:
                    if e.error_code == u'InvalidGroup.NotFound':
                        self.state = self.Missing
                    else:
                        raise

        if self.state == self.MISSING or self.state == self.UNKNOWN:
            self._connect()
            try:
                self.logger.log("creating EC2 placement group ‘{0}’...".format(self.placement_group_name))
                created = self._conn.create_placement_group(self.placement_group_name, self.placement_group_strategy)
            except boto.exception.EC2ResponseError as e:
                if self.state != self.UNKNOWN or e.error_code != u'InvalidGroup.Duplicate':
                    raise

        self.state = self.UP

    def after_activation(self, defn):
        region = self.region
        self._connect()
        conn = self._conn
        for group in self.old_placement_groups:
            if group['region'] != region:
                region = group['region']
                conn = nixops.ec2_utils.connect(region, self.access_key_id)
            try:
                conn.delete_placement_group(group['name'])
            except boto.exception.EC2ResponseError as e:
                if e.error_code != u'InvalidGroup.NotFound':
                    raise
        self.old_placement_groups = []

    def destroy(self, wipe=False):
        if self.state == self.UP or self.state == self.STARTING:
            self.logger.log("deleting EC2 placement group `{0}'...".format(self.placement_group_name))
            self._connect()
            self._conn.delete_placement_group(self.placement_group_name)
            self.state = self.MISSING
        return True
