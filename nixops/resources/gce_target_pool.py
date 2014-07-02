# -*- coding: utf-8 -*-

# Automatic provisioning of GCE Target Pools

import os
import libcloud.common.google

from nixops.resources.gce_http_health_check import GCEHTTPHealthCheckState
from nixops.util import attr_property
from nixops.gce_common import ResourceDefinition, ResourceState, optional_string

class GCETargetPoolDefinition(ResourceDefinition):
    """Definition of a GCE Target Pool"""

    @classmethod
    def get_type(cls):
        return "gce-target-pool"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.targetpool_name = xml.find("attrs/attr[@name='name']/string").get("value")
        self.region = xml.find("attrs/attr[@name='region']/string").get("value")
        self.healthcheck = ( optional_string(xml.find("attrs/attr[@name='healthCheck']/string")) or
            optional_string(xml.find("attrs/attr[@name='healthCheck']/attrs/attr[@name='name']/string")) )

        def machine_to_url(xml):
            spec = xml.find("attr[@name='gce']")
            if spec is None: return None
            return( "https://www.googleapis.com/compute/v1/projects/{0}/zones/{1}/instances/{2}"
                    .format(self.project,
                            spec.find("attrs/attr[@name='region']/string").get("value"),
                            spec.find("attrs/attr[@name='machineName']/string").get("value")) )

        mlist = xml.find("attrs/attr[@name='machines']/list")
        self.machines = list(set( [ machine_to_url(e) for e in mlist.findall("attrs") ] +
                                  [ e.get("value")    for e in mlist.findall("string") ] ))

        if not all(m for m in self.machines):
            raise Exception("Target pool machine specification must be either a NixOps "
                            "machine resource or a fully-qualified GCE resource URL")

        # FIXME: implement backup pool, failover ratio, description, sessionAffinity


    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region)


class GCETargetPoolState(ResourceState):
    """State of a GCE Target Pool"""

    targetpool_name = attr_property("gce.name", None)
    region = attr_property("gce.region", None)
    healthcheck = attr_property("gce.healthcheck", None)
    machines = attr_property("gce.machines", [], 'json')

    @classmethod
    def get_type(cls):
        return "gce-target-pool"

    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)

    def show_type(self):
        s = super(GCETargetPoolState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return self.targetpool_name

    nix_name = "gceTargetPools"

    @property
    def full_name(self):
        return "GCE Target Pool '{0}'".format(self.targetpool_name)

    def targetpool(self):
        return self.connect().ex_get_targetpool(self.targetpool_name)

    def copy_properties(self, defn):
        self.region = defn.region
        self.healthcheck = defn.healthcheck

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_project_change(defn)
        self.no_region_change(defn)

        self.copy_credentials(defn)
        self.targetpool_name = defn.targetpool_name

        if check:
            try:
                tp = self.targetpool()
                if self.state == self.UP:

                    normalized_hc = (tp.healthchecks[0].name if tp.healthchecks else None)
                    self.healthcheck = self.warn_if_changed(self.healthcheck, normalized_hc, 'health check')

                    normalized_machines = set([ n.extra['selfLink'] if hasattr(n, 'extra') else n
                                                for n in tp.nodes ])
                    machines_state = set(self.machines)
                    if machines_state != normalized_machines:
                        if normalized_machines - machines_state:
                            self.warn("{0} contains unexpected machines: {1}".
                                      format(self.full_name, list(normalized_machines - machines_state)))
                        if machines_state - normalized_machines:
                            self.warn("{0} is missing machines: {1}".
                                      format(self.full_name, list(machines_state - normalized_machines)))
                        self.machines = list(normalized_machines)

                else:
                    self.warn("{0} exists, but isn't supposed to. Probably, this is  the result "
                              "of a botched creation attempt and can be fixed by deletion."
                              .format(self.full_name))
                    self.confirm_destroy(tp, self.full_name)

            except libcloud.common.google.ResourceNotFoundError:
                self.warn_missing_resource()

        if self.state != self.UP:
            self.log_start("Creating {0}...".format(self.full_name))
            try:
                tp = self.connect().ex_create_targetpool(defn.targetpool_name, region = defn.region,
                                                         healthchecks = ([ defn.healthcheck ] if defn.healthcheck else None) )
            except libcloud.common.google.ResourceExistsError:
                raise Exception("Tried creating a target pool that already exists. Please run ‘deploy --check’ to fix this.")

            self.log_end("done.")

            self.state = self.UP
            self.copy_properties(defn)
            self.machines = []

        # update the target pool resource if its definition and state are out of sync
        machines_state = set(self.machines)
        machines_defn = set(defn.machines)
        if self.healthcheck != defn.healthcheck or machines_state != machines_defn:
            try:
                tp = self.targetpool()
            except libcloud.common.google.ResourceNotFoundError:
                raise Exception("{0} has been deleted behind our back. Please run ‘deploy --check’ to fix this.".format(self.full_name))

            if self.healthcheck != defn.healthcheck:
                self.log("Updating healthCheck of {0}...".format(self.full_name))
                if self.healthcheck:
                    tp.remove_healthcheck(self.healthcheck)
                    self.healthcheck = None
                if defn.healthcheck:
                    tp.add_healthcheck(defn.healthcheck)
                    self.healthcheck = defn.healthcheck

            if machines_state != machines_defn:
                self.log("Updating machine list of {0}...".format(self.full_name))
                for uri in (machines_state - machines_defn):
                    tp.remove_node(uri)
                    machines_state.remove(uri)
                for uri in (machines_defn - machines_state):
                    tp.add_node(uri)
                    machines_state.add(uri)
                self.machines = list(machines_state)

    def destroy(self, wipe=False):
        if self.state == self.UP:
            try:
                targetpool = self.targetpool()
                return self.confirm_destroy(targetpool, self.full_name, abort = False)
            except libcloud.common.google.ResourceNotFoundError:
                self.warn("Tried to destroy {0} which didn't exist".format(self.full_name))
        return True


    def create_after(self, resources):
        return {r for r in resources if
                isinstance(r, GCEHTTPHealthCheckState)}
