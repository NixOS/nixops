# -*- coding: utf-8 -*-

# Automatic provisioning of GCE Routes.

import libcloud.common.google

from nixops import backends
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

    def create_after(self, resources, defn):
        return {r for r in resources if isinstance(r, backends.MachineState)}

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

    def _get_machine_property(self, machine_name, property):
        """Get a property from the machine """
        machine = self.depl.get_machine(machine_name)
        return getattr(machine, property)

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

        if defn.destination.startswith("res-"):
            # if a machine resource was used for the destination, get
            # the public IP of the instance into the definition of the
            # route
            machine_name = defn.destination[4:]
            defn.destination = "{ip}/32".format(ip=self._get_machine_property(machine_name, "public_ipv4"))

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

                if defn.nextHop and defn.nextHop.startswith("res-"):
                    try:
                        nextHop_name = self._get_machine_property(defn.nextHop[4:], "machine_name")
                        defn.nextHop = self.connect().ex_get_node(nextHop_name)
                    except AttributeError:
                        raise Exception("nextHop can only be a GCE machine.")
                        raise
                    except libcloud.common.google.ResourceNotFoundError:
                        raise Exception("The machine {0} isn't deployed, it need to be before it's added as nextHop".format(nextHop_name))

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
