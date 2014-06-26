# -*- coding: utf-8 -*-

# Automatic provisioning of GCE HTTP Health Checks

import os
import libcloud.common.google

from nixops.util import attr_property
from nixops.gce_common import ResourceDefinition, ResourceState, optional_string


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

    def nix_name(self):
        return "gceHTTPHealthChecks"

    def healthcheck(self):
        return self.connect().ex_get_healthcheck(self.healthcheck_name)

    def copy_properties(self, defn):
        self.host = defn.host
        self.path = defn.path
        self.port = defn.port
        self.description = defn.description
        self.check_interval = defn.check_interval
        self.timeout = defn.timeout
        self.unhealthy_threshold = defn.unhealthy_threshold
        self.healthy_threshold = defn.healthy_threshold

    def create(self, defn, check, allow_reboot, allow_recreate):
        if self.state == self.UP:
            if self.project != defn.project:
                raise Exception("cannot change the project of a deployed GCE HTTP Health Check")

            # Undocumented: as of 26.06.2014, changing port via update() silently ignores the new value.
            if self.port != defn.port:
                raise Exception("cannot change the port of a deployed GCE HTTP Health Check")

        self.copy_credentials(defn)
        self.healthcheck_name = defn.healthcheck_name

        if check:
            try:
                hc = self.healthcheck()
                if self.state == self.UP:

                    if self.host != hc.extra['host']:
                        self.warn("GCE HTTP Health Check '{0}' host has changed to '{1}'. Expected it to be '{2}'".
                                  format(defn.healthcheck_name, hc.extra['host'], self.host))
                        self.host = hc.extra['host']

                    if self.description != hc.extra['description']:
                        self.warn("GCE HTTP Health Check '{0}' description has changed to '{1}'. Expected it to be '{2}'".
                                  format(defn.healthcheck_name, hc.extra['description'], self.description))
                        self.description = hc.extra['description']

                    if self.path != hc.path:
                        self.warn("GCE HTTP Health Check '{0}' path has changed to '{1}'. Expected it to be '{2}'".
                                  format(defn.healthcheck_name, hc.path, self.path))
                        self.path = hc.path

                    if self.port != hc.port:
                        self.warn("GCE HTTP Health Check '{0}' port has changed to '{1}'. Expected it to be '{2}'".
                                  format(defn.healthcheck_name, hc.port, self.port))
                        self.port = hc.port

                    if self.check_interval != hc.interval:
                        self.warn("GCE HTTP Health Check '{0}' check interval has changed to '{1}'. Expected it to be '{2}'".
                                  format(defn.healthcheck_name, hc.interval, self.check_interval))
                        self.check_interval = hc.interval

                    if self.timeout != hc.timeout:
                        self.warn("GCE HTTP Health Check '{0}' timeout has changed to '{1}'. Expected it to be '{2}'".
                                  format(defn.healthcheck_name, hc.timeout, self.timeout))
                        self.timeout = hc.timeout

                    if self.unhealthy_threshold != hc.unhealthy_threshold:
                        self.warn("GCE HTTP Health Check '{0}' unhealthy threshold has changed to '{1}'. Expected it to be '{2}'".
                                  format(defn.healthcheck_name, hc.unhealthy_threshold, self.unhealthy_threshold))
                        self.unhealthy_threshold = hc.unhealthy_threshold

                    if self.healthy_threshold != hc.healthy_threshold:
                        self.warn("GCE HTTP Health Check '{0}' healthy threshold has changed to '{1}'. Expected it to be '{2}'".
                                  format(defn.healthcheck_name, hc.healthy_threshold, self.healthy_threshold))
                        self.healthy_threshold = hc.healthy_threshold

                else:
                    self.warn("GCE HTTP Health Check ‘{0}’ exists, but isn't supposed to. Probably, this is  the result "
                              "of a botched creation attempt and can be fixed by deletion."
                              .format(defn.healthcheck_name))
                    if self.depl.logger.confirm("Are you sure you want to destroy the existing HTTP health check ‘{0}’?".format(defn.healthcheck_name)):
                        self.log_start("destroying...")
                        hc.destroy()
                        self.log_end("done.")
                    else: raise Exception("Can't proceed further.")

            except libcloud.common.google.ResourceNotFoundError:
                if self.state == self.UP:
                    self.warn("GCE HTTP Health Check ‘{0}’ is supposed to exist, but is missing. Recreating...".format(defn.healthcheck_name))
                    self.state = self.MISSING

        if self.state != self.UP:
            self.log_start("Creating GCE HTTP Health Check ‘{0}’...".format(defn.healthcheck_name))
            try:
                # BUG: libcloud as of 0.15.0 doesn't let you specify description when creating a healthcheck,
                # but lets you set it during update.
                # FIXME: set decription property on creation
                healthcheck = self.connect().ex_create_healthcheck(defn.healthcheck_name, host = defn.host,
                                                               path = defn.path, port = defn.port,
                                                               interval = defn.check_interval,
                                                               timeout = defn.timeout,
                                                               unhealthy_threshold = defn.unhealthy_threshold,
                                                               healthy_threshold = defn.healthy_threshold)

            except libcloud.common.google.ResourceExistsError:
                raise Exception("Tried creating a health check that already exists. Please run ‘deploy --check’ to fix this.")

            self.log_end("done.")

            self.state = self.UP
            self.copy_properties(defn)
            self.description = None # trigger setting description via update() for health checks that specify one

        # update the health check resource if its definition and state are out of sync
        if( self.host != defn.host or self.path != defn.path or self.port != defn.port
         or self.check_interval != defn.check_interval or self.timeout != defn.timeout
         or self.description != defn.description
         or self.unhealthy_threshold != defn.unhealthy_threshold
         or self.healthy_threshold != defn.healthy_threshold):
            self.log("Updating parameters of GCE HTTP Health Check ‘{0}’...".format(defn.healthcheck_name))
            try:
                hc = self.healthcheck()
                hc.path = defn.path
                hc.post = defn.port
                hc.interval = defn.check_interval
                hc.timeout = defn.timeout
                hc.unhealthy_threshold = defn.unhealthy_threshold
                hc.healthy_threshold = defn.healthy_threshold
                hc.extra['host'] = defn.host
                hc.extra['description'] = defn.description
                hc.update()
                self.copy_properties(defn)
            except libcloud.common.google.ResourceNotFoundError:
                raise Exception("The HTTP Health Check '{0}' has been deleted behind our back. Please run ‘deploy --check’ to fix this.".format(defn.healthcheck_name))


    def destroy(self, wipe=False):
        if self.state == self.UP:
            try:
                healthcheck = self.healthcheck()
                if not self.depl.logger.confirm("Are you sure you want to destroy GCE HTTP Health Check ‘{0}’?".format(self.healthcheck_name)):
                    return False
                self.log("Destroying GCE HTTP Health Check ‘{0}’...".format(self.healthcheck_name))
                healthcheck.destroy()
            except libcloud.common.google.ResourceNotFoundError:
                self.warn("Tried to destroy GCE HTTP Health Check ‘{0}’ which didn't exist".format(self.healthcheck_name))
        return True
