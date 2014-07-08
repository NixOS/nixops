# -*- coding: utf-8 -*-

# Automatic provisioning of GCE HTTP Health Checks

import os
import libcloud.common.google

from nixops.util import attr_property
from nixops.gce_common import ResourceDefinition, ResourceState, optional_string, ensure_not_empty, ensure_positive


class GCEHTTPHealthCheckDefinition(ResourceDefinition):
    """Definition of a GCE HTTP Health Check"""

    @classmethod
    def get_type(cls):
        return "gce-http-health-check"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.healthcheck_name = xml.find("attrs/attr[@name='name']/string").get("value")
        self.host = optional_string(xml.find("attrs/attr[@name='host']/string"))
        self.path = xml.find("attrs/attr[@name='path']/string").get("value")
        self.port = int(xml.find("attrs/attr[@name='port']/int").get("value"))
        self.check_interval = int(xml.find("attrs/attr[@name='checkInterval']/int").get("value"))
        self.timeout = int(xml.find("attrs/attr[@name='timeout']/int").get("value"))
        self.unhealthy_threshold = int(xml.find("attrs/attr[@name='unhealthyThreshold']/int").get("value"))
        self.healthy_threshold = int(xml.find("attrs/attr[@name='healthyThreshold']/int").get("value"))
        self.description = optional_string(xml.find("attrs/attr[@name='description']/string"))

        ensure_not_empty(self.path, "HTTP Health Check path")
        ensure_positive(self.port, "HTTP Health Check port")
        ensure_positive(self.check_interval, "HTTP Health Check interval")
        ensure_positive(self.timeout, "HTTP Health Check timeout")
        ensure_positive(self.unhealthy_threshold, "HTTP Health Check unhealthy threshold")
        ensure_positive(self.healthy_threshold, "HTTP Health Check healthy threshold")

    def show_type(self):
        return "{0} [:{1}{2}]".format(self.get_type(), self.port, self.path)


class GCEHTTPHealthCheckState(ResourceState):
    """State of a GCE HTTP Health Check"""

    healthcheck_name = attr_property("gce.name", None)
    host = attr_property("gce.host", None)
    path = attr_property("gce.path", None)
    port = attr_property("gce.port", None, int)
    description = attr_property("gce.description", None)
    check_interval = attr_property("gce.checkInterval", None, int)
    timeout = attr_property("gce.timeout", None, int)
    unhealthy_threshold = attr_property("gce.unhealthyThreshold", None, int)
    healthy_threshold = attr_property("gce.healthyThreshold", None, int)

    @classmethod
    def get_type(cls):
        return "gce-http-health-check"


    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)

    def show_type(self):
        s = super(GCEHTTPHealthCheckState, self).show_type()
        if self.state == self.UP: s = "{0} [:{1}{2}]".format(s, self.port,self.path)
        return s

    @property
    def resource_id(self):
        return self.healthcheck_name

    nix_name = "gceHTTPHealthChecks"

    @property
    def full_name(self):
        return "GCE HTTP Health Check '{0}'".format(self.healthcheck_name)

    def healthcheck(self):
        return self.connect().ex_get_healthcheck(self.healthcheck_name)

    defn_properties = [ 'host', 'path', 'port', 'description', 'check_interval',
                        'timeout', 'unhealthy_threshold', 'healthy_threshold' ]

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_project_change(defn)

        self.copy_credentials(defn)
        self.healthcheck_name = defn.healthcheck_name

        if check:
            try:
                hc = self.healthcheck()
                if self.state == self.UP:

                    self.host = self.warn_if_changed(self.host, hc.extra['host'], 'host')
                    self.path = self.warn_if_changed(self.path, hc.path, 'path')
                    self.port = self.warn_if_changed(self.port, hc.port, 'port')
                    self.timeout = self.warn_if_changed(self.timeout, hc.timeout, 'timeout')
                    self.description = self.warn_if_changed(self.description, hc.extra['description'], 'description')
                    self.check_interval = self.warn_if_changed(self.check_interval, hc.interval, 'check interval')
                    self.healthy_threshold = self.warn_if_changed(self.healthy_threshold, hc.healthy_threshold,
                                                                  'healthy threshold')
                    self.unhealthy_threshold = self.warn_if_changed(self.unhealthy_threshold, hc.unhealthy_threshold,
                                                                    'unhealthy threshold')
                else:
                    self.warn_not_supposed_to_exist()
                    self.confirm_destroy(hc, self.full_name)

            except libcloud.common.google.ResourceNotFoundError:
                self.warn_missing_resource()

        if self.state != self.UP:
            self.log_start("Creating {0}...".format(self.full_name))
            try:
                healthcheck = self.connect().ex_create_healthcheck(defn.healthcheck_name, host = defn.host,
                                                                   path = defn.path, port = defn.port,
                                                                   interval = defn.check_interval,
                                                                   timeout = defn.timeout,
                                                                   unhealthy_threshold = defn.unhealthy_threshold,
                                                                   healthy_threshold = defn.healthy_threshold,
                                                                   description = defn.description)
            except libcloud.common.google.ResourceExistsError:
                raise Exception("Tried creating a health check that already exists. "
                                "Please run 'deploy --check' to fix this.")

            self.log_end("done.")
            self.state = self.UP
            self.copy_properties(defn)

        # update the health check resource if its definition and state are out of sync
        if self.properties_changed(defn):
            self.log("Updating parameters of {0}...".format(self.full_name))
            try:
                hc = self.healthcheck()
                hc.path = defn.path
                hc.port = defn.port
                hc.interval = defn.check_interval
                hc.timeout = defn.timeout
                hc.unhealthy_threshold = defn.unhealthy_threshold
                hc.healthy_threshold = defn.healthy_threshold
                hc.extra['host'] = defn.host
                hc.extra['description'] = defn.description
                hc.update()
                self.copy_properties(defn)
            except libcloud.common.google.ResourceNotFoundError:
                raise Exception("{0} has been deleted behind our back. "
                                "Please run 'deploy --check' to fix this."
                                .format(self.full_name))


    def destroy(self, wipe=False):
        if self.state == self.UP:
            try:
                healthcheck = self.healthcheck()
                return self.confirm_destroy(healthcheck, self.full_name, abort = False)
            except libcloud.common.google.ResourceNotFoundError:
                self.warn("Tried to destroy {0} which didn't exist".format(self.full_name))
        return True
