# -*- coding: utf-8 -*-

# Automatic provisioning of GCE Routes.

import libcloud.common.google

from nixops.util import attr_property
from nixops.gce_common import ResourceDefinition, ResourceState


class GCERouteDefinition(ResourceDefinition):
    """Definition of a GCE Route"""

    @classmethod
    def get_type(cls):
        return "gce-route"

    @classmethod
    def get_resource_type(cls):
        return "gceRoutes"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.route_name = self.get_option_value(xml, 'name', str)
        self.description = self.get_option_value(xml, 'description', str, optional=True)
        self.network = self.get_option_value(xml, 'network', str)
        self.priority = self.get_option_value(xml, 'priority', int)
        self.nextHop = self.get_option_value(xml, 'nextHop', str, optional=True)
        self.destination = self.get_option_value(xml, 'destination', str)
        self.tags = self.get_option_value(xml, 'tags', "strlist", optional=True)

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.name)


class GCERouteState(ResourceState):
    """State of a GCE Route"""

    route_name = attr_property("gce.route.name", None)
    description = attr_property("gce.route.description", None)
    network = attr_property("gce.route.network", None)
    priority = attr_property("gce.route.priority", None)
    nextHop = attr_property("gce.route.nextHop", None)
    destination = attr_property("gce.route.destination", None)
    # TODO: Store tags in the state file.
    tags = attr_property("gce.route.tags", None)

    defn_properties = ['route_name', 'priority', 'destination', 'nextHop', 'network', 'description']

    nix_name = "gceRoutes"

    @classmethod
    def get_type(cls):
        return "gce-route"

    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)

    def show_type(self):
        s = super(GCERouteState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.name)
        return s


    @property
    def full_name(self):
        return "GCE route '{0}'".format(self.name)

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.copy_credentials(defn)

        if self.state != self.UP:
            with self.depl._db:
                self.log("creating {0}...".format(self.full_name))
                self.copy_properties(defn)
                try:
                    route = self.connect().ex_create_route(defn.route_name, defn.destination, defn.priority, defn.network, defn.tags, defn.nextHop, defn.description)
                except libcloud.common.google.ResourceExistsError:
                    raise Exception("tried creating a route that already exists.")
                self.state = self.UP

    def destroy(self, wipe=False):
        if self.state == self.UP:
            try:
                route = self.connect().ex_get_route(self.route_name)
                if not self.depl.logger.confirm("are you sure you want to destroy {0}?".format(self.full_name)):
                    return False

                self.log("destroying {0}...".format(self.full_name))
                route.destroy()
            except libcloud.common.google.ResourceNotFoundError:
                self.warn("tried to destroy {0} which didn't exist".format(self.full_name))
        return True
