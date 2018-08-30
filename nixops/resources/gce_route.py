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
    priority = attr_property("gce.route.priority", None, int)
    nextHop = attr_property("gce.route.nextHop", None)
    destination = attr_property("gce.route.destination", None)
    tags = attr_property("gce.route.tags", None, 'json')

    defn_properties = ['route_name', 'destination', 'priority', 'network', 'tags', 'nextHop', 'description']

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

    def _destroy_route(self):
        try:
            route = self.connect().ex_get_route(self.route_name)
            route.destroy()
        except libcloud.common.google.ResourceNotFoundError:
            self.warn("tried to destroy {0} which didn't exist".format(self.full_name))

    @property
    def full_name(self):
        return "GCE route '{0}'".format(self.name)

    def _route_is_missing(self):
        try:
            self.connect().ex_get_route(self.route_name)
            return False
        except libcloud.common.google.ResourceNotFoundError:
            return True

    def _real_state_differ(self):
        """ Check If any of the route's properties has a different value than that in the state"""
        route = self.connect().ex_get_route(self.route_name)
        # libcloud only expose these properties in the GCERoute class.
        # "description" and "nextHop" can't be checked.
        route_properties = {"name": "route_name",
                            "dest_range": "destination",
                            "tags": "tags",
                            "priority": "priority"}
        # This shouldn't happen, unless you delete the
        # route manually and create another one with the
        # same name, but different properties.
        real_state_differ = any([getattr(route, route_attr) != getattr(self, self_attr)
                                 for route_attr, self_attr in route_properties.iteritems()])

        # We need to check the network in separate, since GCE API add the project and the region
        network_differ = route.network.split("/")[-1] != self.network

        return real_state_differ or network_differ

    def _check(self):

        if self._route_is_missing():
            self.state = self.MISSING
            return False

        if self._real_state_differ():
                if self.depl.logger.confirm("Route properties are different from those in the state, "
                                            "destroy route {0}?".format(self.route_name)):
                    self._destroy_route()
                    self.state = self.MISSING
        return True

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.copy_credentials(defn)

        if check:
            if self._route_is_missing():
                self.state = self.MISSING

            elif self._real_state_differ():
                if allow_recreate:
                    self._destroy_route()
                    self.state = self.MISSING
                else:
                    self.warn("Route properties are different from those in the state,"
                              " use --allow-recreate to delete the route and deploy it again.")

        if self.is_deployed() and self.properties_changed(defn):
            if allow_recreate:
                self.log("deleting route {0}...".format(self.route_name))
                self._destroy_route()
                self.state = self.MISSING
            else:
                raise Exception("GCE routes are immutable, you need to use --allow-recreate.")

        if self.state != self.UP:
            with self.depl._db:
                self.log("creating {0}...".format(self.full_name))
                self.copy_properties(defn)
                args = [getattr(defn, attr) for attr in self.defn_properties]
                try:
                    self.connect().ex_create_route(*args)
                except libcloud.common.google.ResourceExistsError:
                    raise Exception("tried creating a route that already exists.")
                self.state = self.UP

    def destroy(self, wipe=False):
        if self.state == self.UP:
            if not self.depl.logger.confirm("are you sure you want to destroy {0}?".format(self.full_name)):
                return False

            self.log("destroying {0}...".format(self.full_name))
            self._destroy_route()

        return True
