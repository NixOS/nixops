# -*- coding: utf-8 -*-

# Automatic provisioning of GCE Forwarding Rules

import os
import libcloud.common.google


from nixops.resources.gce_static_ip import GCEStaticIPState
from nixops.resources.gce_target_pool import GCETargetPoolState
from nixops.util import attr_property
from nixops.gce_common import ResourceDefinition, ResourceState, optional_string, ensure_not_empty


class GCEForwardingRuleDefinition(ResourceDefinition):
    """Definition of a GCE Forwarding Rule"""

    @classmethod
    def get_type(cls):
        return "gce-forwarding-rule"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.forwarding_rule_name = xml.find("attrs/attr[@name='name']/string").get("value")
        self.region = xml.find("attrs/attr[@name='region']/string").get("value")
        self.protocol = xml.find("attrs/attr[@name='protocol']/string").get("value")

        pr = optional_string(xml.find("attrs/attr[@name='portRange']/string"))
        self.port_range = None if pr is None else "{0}-{1}".format(pr, pr) if pr.isdigit() else pr

        self.description = optional_string(xml.find("attrs/attr[@name='description']/string"))
        self.ipAddress = ( optional_string(xml.find("attrs/attr[@name='ipAddress']/string")) or
                           optional_string(xml.find("attrs/attr[@name='ipAddress']/attrs/attr[@name='name']/string")) )
        self.target_pool = ( optional_string(xml.find("attrs/attr[@name='targetPool']/string")) or
                            optional_string(xml.find("attrs/attr[@name='targetPool']/attrs/attr[@name='name']/string")) )

        ensure_not_empty(self.target_pool, "Forwarding Rule target pool")

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region)


class GCEForwardingRuleState(ResourceState):
    """State of a GCE Forwarding Rule"""

    forwarding_rule_name = attr_property("gce.name", None)
    target_pool = attr_property("gce.targetPool", None)
    region = attr_property("gce.region", None)
    protocol = attr_property("gce.protocol", None)
    port_range = attr_property("gce.portRange", None)
    ipAddress = attr_property("gce.ipAddress", None)
    description = attr_property("gce.description", None)
    public_ipv4 = attr_property("gce.public_ipv4", None)

    @classmethod
    def get_type(cls):
        return "gce-forwarding-rule"

    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)

    def show_type(self):
        s = super(GCEForwardingRuleState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return self.forwarding_rule_name

    nix_name = "gceForwardingRules"

    @property
    def full_name(self):
        return "GCE Forwarding Rule '{0}'".format(self.forwarding_rule_name)

    def forwarding_rule(self):
        return self.connect().ex_get_forwarding_rule(self.forwarding_rule_name)

    defn_properties = [ 'target_pool', 'region', 'protocol',
                        'port_range', 'ipAddress', 'description' ]

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_change(self.target_pool != defn.target_pool, 'target pool')
        self.no_change(self.protocol != defn.protocol, 'protocol')
        self.no_change(self.port_range != defn.port_range, 'port range')
        self.no_change(self.ipAddress != defn.ipAddress, 'address')
        self.no_change(self.description != defn.description, 'description')
        self.no_project_change(defn)
        self.no_region_change(defn)

        self.copy_credentials(defn)
        self.forwarding_rule_name = defn.forwarding_rule_name

        if check:
            try:
                fwr = self.forwarding_rule()
                if self.state == self.UP:
                    self.handle_changed_property('public_ipv4', fwr.address, property_name = 'IP address')

                    self.handle_changed_property('region', fwr.region.name, can_fix = False)
                    self.handle_changed_property('target_pool', fwr.targetpool.name, can_fix = False)
                    self.handle_changed_property('protocol', fwr.protocol, can_fix = False)
                    self.handle_changed_property('description', fwr.extra['description'], can_fix = False)
                    self.warn_if_changed(self.port_range or '1-65535', fwr.extra['portRange'],
                                         'port range', can_fix = False)
                else:
                    self.warn_not_supposed_to_exist()
                    self.confirm_destroy(fwr, self.full_name)

            except libcloud.common.google.ResourceNotFoundError:
                self.warn_missing_resource()

        if self.state != self.UP:
            self.log_start("Creating {0}...".format(self.full_name))
            try:
                fwr = self.connect().ex_create_forwarding_rule(defn.forwarding_rule_name,
                                                               defn.target_pool, region = defn.region,
                                                               protocol = defn.protocol,
                                                               port_range = defn.port_range,
                                                               address = defn.ipAddress,
                                                               description = defn.description)
            except libcloud.common.google.ResourceExistsError:
                raise Exception("Tried creating a forwarding rule that already exists. "
                                "Please run 'deploy --check' to fix this.")

            self.log_end("done.")
            self.state = self.UP
            self.copy_properties(defn)
            self.public_ipv4 = fwr.address
            self.log("got IP: {0}".format(self.public_ipv4))

        # only changing of target pool is supported by GCE, but not libcloud
        # FIXME: implement


    def destroy(self, wipe=False):
        if self.state == self.UP:
            try:
                fwr = self.forwarding_rule()
                return self.confirm_destroy(fwr, self.full_name, abort = False)
            except libcloud.common.google.ResourceNotFoundError:
                self.warn("Tried to destroy {0} which didn't exist".format(self.full_name))
        return True

    def create_after(self, resources):
        return {r for r in resources if
                isinstance(r, GCETargetPoolState) or
                isinstance(r, GCEStaticIPState)}
