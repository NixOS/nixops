# -*- coding: utf-8 -*-

# Automatic provisioning of Azure network security groups.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState, ResId, normalize_location

from azure.mgmt.network import *

class AzureNetworkSecurityGroupDefinition(ResourceDefinition):
    """Definition of an Azure Network Security Group"""

    @classmethod
    def get_type(cls):
        return "azure-network-security-group"

    @classmethod
    def get_resource_type(cls):
        return "azureSecurityGroups"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.nsg_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'resourceGroup', 'resource')
        self.copy_location(xml)
        self.copy_tags(xml)

        self.security_rules = {
            _r.get("name"): self._parse_security_rule(_r)
            for _r in xml.findall("attrs/attr[@name='securityRules']/attrs/attr")
        }

    def _parse_security_rule(self, xml):
        return {
            'description': self.get_option_value(xml, 'description', str),
            'protocol': self.get_option_value(xml, 'protocol', str),
            'source_port_range': self.get_option_value(xml, 'sourcePortRange', str),
            'destination_port_range': self.get_option_value(xml, 'destinationPortRange', str),
            'source_address_prefix': self.get_option_value(xml, 'sourceAddressPrefix', str),
            'destination_address_prefix': self.get_option_value(xml, 'destinationAddressPrefix', str),
            'access': self.get_option_value(xml, 'access', str),
            'priority': self.get_option_value(xml, 'priority', int),
            'direction': self.get_option_value(xml, 'direction', str),
        }

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.location)


class AzureNetworkSecurityGroupState(ResourceState):
    """State of an Azure Network Security Group"""

    nsg_name = attr_property("azure.name", None)
    resource_group = attr_property("azure.resourceGroup", None)
    location = attr_property("azure.location", None)
    tags = attr_property("azure.tags", {}, 'json')
    security_rules = attr_property("azure.securityRules", {}, 'json')

    @classmethod
    def get_type(cls):
        return "azure-network-security-group"

    def show_type(self):
        s = super(AzureNetworkSecurityGroupState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.location)
        return s

    @property
    def resource_id(self):
        return self.nsg_name

    @property
    def full_name(self):
        return "Azure network security group '{0}'".format(self.resource_id)

    def get_resource(self):
        try:
            return self.nrpc().network_security_groups.get(
                       self.resource_group, self.resource_id).network_security_group
        except azure.common.AzureMissingResourceHttpError:
            return None

    def destroy_resource(self):
        self.nrpc().network_security_groups.delete(
            self.resource_group, self.resource_id)

    defn_properties = [ 'location', 'tags', 'security_rules' ]

    def _create_or_update(self, defn):
        self.nrpc().network_security_groups.create_or_update(
            defn.resource_group, defn.nsg_name,
            NetworkSecurityGroup(
                location = defn.location,
                security_rules = [
                    SecurityRule(
                        name = _name,
                        description = _r['description'],
                        protocol = _r['protocol'],
                        source_port_range = _r['source_port_range'],
                        destination_port_range = _r['destination_port_range'],
                        source_address_prefix = _r['source_address_prefix'],
                        destination_address_prefix = _r['destination_address_prefix'],
                        access = _r['access'],
                        priority = _r['priority'],
                        direction = _r['direction'],
                    ) for _name, _r in defn.security_rules.iteritems()
                ],
                tags = defn.tags))
        self.state = self.UP
        self.copy_properties(defn)


    def handle_changed_security_rules(self, rules):
        def update_rules(k, v):
            x = self.security_rules
            if v == None:
                x.pop(k, None)
            else:
                x[k] = v
            self.security_rules = x

        for _rule in rules:
            _s_name = next((_n for _n, _x in self.security_rules.iteritems() if _n == _rule.name), None)
            if _s_name is None:
                self.warn("found unexpected security rule {0}".format(_rule.name))
                update_rules(_rule.name, {"dummy": True})
        for _name, _s_rule in self.security_rules.iteritems():
            if _s_rule.get("dummy", False): continue
            rule_res_name = "security rule {0}".format(_name)
            rule = next((_r for _r in rules if _r.name == _name), None)
            if rule is None:
                self.warn("{0} has been deleted behind our back".format(rule_res_name))
                update_rules(_name, None)
                continue
            self.handle_changed_dict(_s_rule, 'description',
                                     rule.description,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'protocol',
                                     rule.protocol,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'source_port_range',
                                     rule.source_port_range,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'destination_port_range',
                                     rule.destination_port_range,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'source_address_prefix',
                                     rule.source_address_prefix,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'destination_address_prefix',
                                     rule.destination_address_prefix,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'access',
                                     rule.access,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'priority',
                                     rule.priority,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'direction',
                                     rule.direction,
                                     resource_name = rule_res_name)
            update_rules(_name, _s_rule)


    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_subscription_id_change(defn)
        self.no_property_change(defn, 'location')
        self.no_property_change(defn, 'resource_group')

        self.copy_mgmt_credentials(defn)
        self.nsg_name = defn.nsg_name
        self.resource_group = defn.resource_group

        if check:
            nsg = self.get_settled_resource()
            if not nsg:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.warn_if_failed(nsg)
                self.handle_changed_property('location', normalize_location(nsg.location),
                                             can_fix = False)
                self.handle_changed_property('tags', nsg.tags)
                self.handle_changed_security_rules(nsg.security_rules)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a network security group that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} in {1}...".format(self.full_name, defn.location))
            self._create_or_update(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            self.get_settled_resource_assert_exists()
            self._create_or_update(defn)


    def create_after(self, resources, defn):
        from nixops.resources.azure_resource_group import AzureResourceGroupState
        return {r for r in resources
                  if isinstance(r, AzureResourceGroupState) }
