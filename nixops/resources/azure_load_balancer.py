# -*- coding: utf-8 -*-

# Automatic provisioning of Azure load balancers.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState, ResId, normalize_location

from azure.mgmt.network import *

class AzureLoadBalancerDefinition(ResourceDefinition):
    """Definition of an Azure Load Balancer"""

    @classmethod
    def get_type(cls):
        return "azure-load-balancer"

    @classmethod
    def get_resource_type(cls):
        return "azureLoadBalancers"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.load_balancer_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'resourceGroup', 'resource')
        self.copy_location(xml)

        self.lb_resid = ResId("",
                              subscription = self.get_subscription_id(),
                              group = self.resource_group,
                              provider = 'Microsoft.Network',
                              type = 'loadBalancers',
                              resource = self.load_balancer_name)

        self.copy_option(xml, 'backendAddressPools', 'strlist')

        self.frontend_interfaces = {
            _if.get("name"): self._parse_frontend_interface(_if)
            for _if in xml.findall("attrs/attr[@name='frontendInterfaces']/attrs/attr")
        }
        self.probes = {
            _p.get("name"): self._parse_probe(_p)
            for _p in xml.findall("attrs/attr[@name='probes']/attrs/attr")
        }
        self.load_balancing_rules = {
            _lbr.get("name"): self._parse_lb_rule(_lbr)
            for _lbr in xml.findall("attrs/attr[@name='loadBalancingRules']/attrs/attr")
        }
        self.inbound_nat_rules = {
            _inr.get("name"): self._parse_nat_rule(_inr)
            for _inr in xml.findall("attrs/attr[@name='inboundNatRules']/attrs/attr")
        }
        self.copy_tags(xml)

    def _parse_frontend_interface(self, xml):
        subnet_xml = xml.find("attrs/attr[@name='subnet']")
        assert subnet_xml is not None
        private_ip_address =  self.get_option_value(xml, 'privateIpAddress', str, optional = True)
        private_ip_allocation_method = "Static" if private_ip_address else "Dynamic"
        network = self.get_option_value(subnet_xml, 'network', 'res-id', optional = True)
        subnet = network and ResId(network, subtype = 'subnets',
                                        subresource = self.get_option_value(subnet_xml, 'name', str)).id
        public_ip = self.get_option_value(xml, 'publicIpAddress', 'res-id', optional = True)
        if subnet and public_ip:
            raise Exception('{0}: can specify either subnet or public IP but not both at once'
                            .format(self.load_balancer_name))
        if not subnet and not public_ip:
            raise Exception('{0}: must specify either subnet or public IP'
                            .format(self.load_balancer_name))
        return {
            'private_ip_address': private_ip_address,
            'private_ip_allocation_method': private_ip_allocation_method,
            'public_ip_address': public_ip,
            'subnet': subnet,
        }

    def _parse_probe(self, xml):
        protocol = self.get_option_value(xml, 'protocol', str)
        path = ( self.get_option_value(xml, 'path', str, optional = True)
                 if protocol.lower() == "http" else None )
        return {
            'protocol': protocol,
            'port': self.get_option_value(xml, 'port', int),
            'path': path,
            'interval': self.get_option_value(xml, 'interval', int),
            'number_of_probes': self.get_option_value(xml, 'numberOfProbes', int),
        }

    def _parse_nat_rule(self, xml):
        frontend_interface_name = self.get_option_value(xml, 'frontendInterface', str)
        if frontend_interface_name not in self.frontend_interfaces:
            raise Exception("{0}: referenced frontend interface {1} doesn't exist "
                            .format(self.load_balancer_name, frontend_interface_name))
        return {
            'frontend_interface': ResId(self.lb_resid,
                                        subresource = frontend_interface_name,
                                        subtype = 'frontendIPConfigurations').id,
            'protocol': self.get_option_value(xml, 'protocol', str),
            'frontend_port': self.get_option_value(xml, 'frontendPort', int),
            'backend_port': self.get_option_value(xml, 'backendPort', int),
            'enable_floating_ip': self.get_option_value(xml, 'enableFloatingIp', bool),
            'idle_timeout': self.get_option_value(xml, 'idleTimeout', int),
        }

    def _parse_lb_rule(self, xml):
        probe = self.get_option_value(xml, 'probe', str, optional = True)
        if probe and probe not in self.probes:
            raise Exception("{0}: referenced probe {1} doesn't exist "
                            .format(self.load_balancer_name, probe))

        frontend_interface_name = self.get_option_value(xml, 'frontendInterface', str)
        if frontend_interface_name not in self.frontend_interfaces:
            raise Exception("{0}: referenced frontend interface {1} doesn't exist "
                            .format(self.load_balancer_name, frontend_interface_name))

        backend_pool_name = self.get_option_value(xml, 'backendAddressPool', str)
        if backend_pool_name not in self.backend_address_pools:
            raise Exception("{0}: referenced backend address pool {1} doesn't exist "
                            .format(self.load_balancer_name, backend_pool_name))

        return {
            'frontend_interface': ResId(self.lb_resid,
                                        subresource = frontend_interface_name,
                                        subtype = 'frontendIPConfigurations').id,
            'backend_address_pool': ResId(self.lb_resid,
                                          subresource = backend_pool_name,
                                          subtype = 'backendAddressPools').id,
            'probe': probe and ResId(self.lb_resid, subtype = 'probes',
                                     subresource = probe).id,
            'protocol': self.get_option_value(xml, 'protocol', str),
            'frontend_port': self.get_option_value(xml, 'frontendPort', int),
            'backend_port': self.get_option_value(xml, 'backendPort', int),
            'enable_floating_ip': self.get_option_value(xml, 'enableFloatingIp', bool),
            'idle_timeout': self.get_option_value(xml, 'idleTimeout', int),
            'load_distribution': self.get_option_value(xml, 'loadDistribution', str),
        }

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.location)


class AzureLoadBalancerState(ResourceState):
    """State of an Azure Load Balancer"""

    load_balancer_name = attr_property("azure.name", None)
    backend_address_pools = attr_property("azure.backendAddressPools", [], 'json')
    frontend_interfaces = attr_property("azure.frontendInterfaces", {}, 'json')
    probes = attr_property("azure.probes", {}, 'json')
    load_balancing_rules = attr_property("azure.loadBalancingRules", {}, 'json')
    inbound_nat_rules = attr_property("azure.inboundNatRules", {}, 'json')
    resource_group = attr_property("azure.resourceGroup", None)
    location = attr_property("azure.location", None)
    tags = attr_property("azure.tags", {}, 'json')

    @classmethod
    def get_type(cls):
        return "azure-load-balancer"

    def show_type(self):
        s = super(AzureLoadBalancerState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.location)
        return s

    @property
    def resource_id(self):
        return self.load_balancer_name

    @property
    def full_name(self):
        return "Azure load balancer '{0}'".format(self.resource_id)

    def get_resource(self):
        try:
            return self.nrpc().load_balancers.get(self.resource_group, self.resource_id).load_balancer
        except azure.common.AzureMissingResourceHttpError:
            return None

    def destroy_resource(self):
        self.nrpc().load_balancers.delete(self.resource_group, self.resource_id)

    defn_properties = [ 'location', 'tags', 'backend_address_pools',  'inbound_nat_rules',
                        'frontend_interfaces', 'probes', 'load_balancing_rules' ]

    def _create_or_update(self, defn):
        self.nrpc().load_balancers.create_or_update(
            defn.resource_group, defn.load_balancer_name,
            LoadBalancer(
                location = defn.location,
                backend_address_pools = [
                    BackendAddressPool(name = _name)
                    for _name in defn.backend_address_pools
                ],
                frontend_ip_configurations = [
                    FrontendIpConfiguration(
                        name = _name,
                        private_ip_address = _if['private_ip_address'],
                        private_ip_allocation_method = _if['private_ip_allocation_method'],
                        subnet = _if['subnet'] and ResId(_if['subnet']),
                        public_ip_address = _if['public_ip_address'] and ResId(_if['public_ip_address']),
                    ) for _name, _if in defn.frontend_interfaces.iteritems()
                ],
                probes = [
                    Probe(
                        name = _name,
                        protocol = _p['protocol'],
                        port = _p['port'],
                        interval_in_seconds = _p['interval'],
                        number_of_probes = _p['number_of_probes'],
                        request_path = _p['path'],
                    ) for _name, _p in defn.probes.iteritems()
                ],
                load_balancing_rules = [
                    LoadBalancingRule(
                        name = _name,
                        frontend_ip_configuration = ResId(_r['frontend_interface']),
                        backend_address_pool = ResId(_r['backend_address_pool']),
                        probe = _r['probe'] and ResId(_r['probe']),
                        protocol = _r['protocol'],
                        load_distribution = _r['load_distribution'],
                        frontend_port = _r['frontend_port'],
                        backend_port = _r['backend_port'],
                        idle_timeout_in_minutes = _r['idle_timeout'],
                        enable_floating_ip = _r['enable_floating_ip'],
                    ) for _name, _r in defn.load_balancing_rules.iteritems()
                ],
                inbound_nat_rules = [
                    InboundNatRule(
                        name = _name,
                        frontend_ip_configuration = ResId(_r['frontend_interface']),
                        protocol = _r['protocol'],
                        frontend_port = _r['frontend_port'],
                        backend_port = _r['backend_port'],
                        idle_timeout_in_minutes = _r['idle_timeout'],
                        enable_floating_ip = _r['enable_floating_ip'],
                    ) for _name, _r in defn.inbound_nat_rules.iteritems()
                ],
                tags = defn.tags))
        self.state = self.UP
        self.copy_properties(defn)


    def handle_changed_probes(self, probes):
        def update_probes(k, v):
            x = self.probes
            if v == None:
                x.pop(k, None)
            else:
                x[k] = v
            self.probes = x

        for _probe in probes:
            _s_name = next((_n for _n, _p in self.probes.iteritems() if _n == _probe.name), None)
            if _s_name is None:
                self.warn("found unexpected probe {0}".format(_probe.name))
                update_probes(_probe.name, {"dummy": True})
        for _name, _s_probe in self.probes.iteritems():
            if _s_probe.get("dummy", False): continue
            probe_res_name = "probe {0}".format(_name)
            probe = next((_p for _p in probes if _p.name == _name), None)
            if probe is None:
                self.warn("probe {0} has been deleted behind our back".format(_name))
                update_probes(_name, None)
                continue
            self.handle_changed_dict(_s_probe, 'protocol', probe.protocol,
                                     resource_name = probe_res_name)
            self.handle_changed_dict(_s_probe, 'port', probe.port,
                                     resource_name = probe_res_name)
            self.handle_changed_dict(_s_probe, 'path', probe.request_path,
                                     resource_name = probe_res_name)
            self.handle_changed_dict(_s_probe, 'interval',
                                     probe.interval_in_seconds,
                                     resource_name = probe_res_name)
            self.handle_changed_dict(_s_probe, 'number_of_probes',
                                     probe.number_of_probes,
                                     resource_name = probe_res_name)
            update_probes(_name, _s_probe)


    def handle_changed_frontend_interfaces(self, interfaces):
        def update_interfaces(k, v):
            x = self.frontend_interfaces
            if v == None:
                x.pop(k, None)
            else:
                x[k] = v
            self.frontend_interfaces = x

        for _if in interfaces:
            _s_name = next((_n for _n, _x in self.frontend_interfaces.iteritems() if _n == _if.name), None)
            if _s_name is None:
                self.warn("found unexpected frontend interface {0}".format(_if.name))
                update_interfaces(_if.name, {"dummy": True})
        for _name, _s_if in self.frontend_interfaces.iteritems():
            if _s_if.get("dummy", False): continue
            if_res_name = "frontend interface {0}".format(_name)
            interface = next((_if for _if in interfaces if _if.name == _name), None)
            if interface is None:
                self.warn("frontend interface {0} has been deleted behind our back".format(_name))
                update_interfaces(_name, None)
                continue
            if _s_if['private_ip_address'] is not None:
                self.handle_changed_dict(_s_if, 'private_ip_address',
                                        interface.private_ip_address,
                                        resource_name = if_res_name)
            self.handle_changed_dict(_s_if, 'private_ip_allocation_method',
                                     interface.private_ip_allocation_method,
                                     resource_name = if_res_name)
            self.handle_changed_dict(_s_if, 'subnet',
                                     interface.subnet and interface.subnet.id,
                                     resource_name = if_res_name)
            self.handle_changed_dict(_s_if, 'public_ip_address',
                                     interface.public_ip_address and
                                     interface.public_ip_address.id,
                                     resource_name = if_res_name)
            update_interfaces(_name, _s_if)


    def handle_changed_lb_rules(self, rules):
        def update_rules(k, v):
            x = self.load_balancing_rules
            if v == None:
                x.pop(k, None)
            else:
                x[k] = v
            self.load_balancing_rules = x

        for _rule in rules:
            _s_name = next((_n for _n, _x in self.load_balancing_rules.iteritems() if _n == _rule.name), None)
            if _s_name is None:
                self.warn("found unexpected load balancing rule {0}".format(_rule.name))
                update_rules(_rule.name, {"dummy": True})
        for _name, _s_rule in self.load_balancing_rules.iteritems():
            if _s_rule.get("dummy", False): continue
            rule_res_name = "load balancing rule {0}".format(_name)
            rule = next((_r for _r in rules if _r.name == _name), None)
            if rule is None:
                self.warn("load balancing rule {0} has been deleted behind our back".format(_name))
                update_rules(_name, None)
                continue
            self.handle_changed_dict(_s_rule, 'frontend_interface',
                                     rule.frontend_ip_configuration.id,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'backend_address_pool',
                                     rule.backend_address_pool.id,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'probe',
                                     rule.probe and rule.probe.id,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'protocol', rule.protocol,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'load_distribution',
                                     rule.load_distribution,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'frontend_port',
                                     rule.frontend_port,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'backend_port',
                                     rule.backend_port,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'idle_timeout',
                                     rule.idle_timeout_in_minutes,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'enable_floating_ip',
                                     rule.enable_floating_ip,
                                     resource_name = rule_res_name)
            update_rules(_name, _s_rule)


    def handle_changed_nat_rules(self, rules):
        def update_rules(k, v):
            x = self.inbound_nat_rules
            if v == None:
                x.pop(k, None)
            else:
                x[k] = v
            self.inbound_nat_rules = x

        for _rule in rules:
            _s_name = next((_n for _n, _x in self.inbound_nat_rules.iteritems() if _n == _rule.name), None)
            if _s_name is None:
                self.warn("found unexpected inbound NAT rule {0}".format(_rule.name))
                update_rules(_rule.name, {"dummy": True})
        for _name, _s_rule in self.inbound_nat_rules.iteritems():
            if _s_rule.get("dummy", False): continue
            rule_res_name = "inbound NAT rule {0}".format(_name)
            rule = next((_r for _r in rules if _r.name == _name), None)
            if rule is None:
                self.warn("{0} has been deleted behind our back".format(rule_res_name))
                update_rules(_name, None)
                continue
            self.handle_changed_dict(_s_rule, 'frontend_interface',
                                     rule.frontend_ip_configuration.id,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'protocol', rule.protocol,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'frontend_port',
                                     rule.frontend_port,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'backend_port',
                                     rule.backend_port,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'idle_timeout',
                                     rule.idle_timeout_in_minutes,
                                     resource_name = rule_res_name)
            self.handle_changed_dict(_s_rule, 'enable_floating_ip',
                                     rule.enable_floating_ip,
                                     resource_name = rule_res_name)
            update_rules(_name, _s_rule)


    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_subscription_id_change(defn)
        self.no_location_change(defn)
        self.no_property_change(defn, 'resource_group')

        self.copy_mgmt_credentials(defn)
        self.load_balancer_name = defn.load_balancer_name
        self.resource_group = defn.resource_group

        if check:
            lb = self.get_settled_resource()
            if not lb:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.warn_if_failed(lb)
                self.handle_changed_property('location', normalize_location(lb.location),
                                             can_fix = False)
                self.handle_changed_property('tags', lb.tags)
                self.handle_changed_probes(lb.probes)
                self.handle_changed_frontend_interfaces(lb.frontend_ip_configurations)
                self.handle_changed_lb_rules(lb.load_balancing_rules)
                self.handle_changed_nat_rules(lb.inbound_nat_rules)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a load balancer that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} in {1}...".format(self.full_name, defn.location))
            self._create_or_update(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            self.get_settled_resource_assert_exists()
            self._create_or_update(defn)


    def create_after(self, resources, defn):
        from nixops.resources.azure_resource_group import AzureResourceGroupState
        from nixops.resources.azure_virtual_network import AzureVirtualNetworkState
        from nixops.resources.azure_reserved_ip_address import AzureReservedIPAddressState
        return {r for r in resources
                  if isinstance(r, AzureResourceGroupState) or isinstance(r, AzureVirtualNetworkState) or
                     isinstance(r, AzureReservedIPAddressState) }
