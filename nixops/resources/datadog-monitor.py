# -*- coding: utf-8 -*-

import nixops.util
import nixops.resources
import nixops.datadog_utils


class DatadogMonitorDefinition(nixops.resources.ResourceDefinition):
    """Definition of a Datadog monitor."""

    @classmethod
    def get_type(cls):
        return "datadog-monitor"

    @classmethod
    def get_resource_type(cls):
        return "datadogMonitors"

    def __init__(self, xml):
        nixops.resources.ResourceDefinition.__init__(self, xml)
        self.monitor_name = xml.find("attrs/attr[@name='name']/string").get("value")
        self.monitor_type = xml.find("attrs/attr[@name='type']/string").get("value")
        self.monitor_query = xml.find("attrs/attr[@name='query']/string").get("value")
        self.api_key = xml.find("attrs/attr[@name='api_key']/string").get("value")
        self.app_key = xml.find("attrs/attr[@name='app_key']/string").get("value")
        self.monitor_message =  xml.find("attrs/attr[@name='message']/string").get("value")

    def show_type(self):
        return "{0}".format(self.get_type())

class DatadogMonitorState(nixops.resources.ResourceState):
    """State of a Datadog monitor"""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    api_key = nixops.util.attr_property("api_key", None)
    app_key = nixops.util.attr_property("app_key", None)
    monitor_name = nixops.util.attr_property("monitor_name", None)
    monitor_type = nixops.util.attr_property("monitor_type", None)
    monitor_query = nixops.util.attr_property("monitor_query", None)
    monitor_message = nixops.util.attr_property("monitor_message", None)
    monitor_id = nixops.util.attr_property("monitor_id", None)

    @classmethod
    def get_type(cls):
        return "datadog-monitor"


    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._dd_api = None
        self._key_options = None


    def show_type(self):
        s = super(DatadogMonitorState, self).show_type()
        return s


    @property
    def resource_id(self):
        return self.monitor_name


    def get_definition_prefix(self):
        return "resources.datadogMonitors."

    def connect(self, app_key, api_key):
        if self._dd_api: return
        self._dd_api, self._key_options = nixops.datadog_utils.initializeDatadog(app_key=app_key, api_key=api_key)

    def create(self, defn, check, allow_reboot, allow_recreate):
        if check or self.state != self.UP:
            self.connect(app_key=defn.app_key, api_key=defn.api_key)
            self.log("creating Datadog monitor '{0}...'".format(defn.monitor_name))
            response = self._dd_api.Monitor.create(
                type=defn.monitor_type, query=defn.monitor_query, name=defn.monitor_name,
                message=defn.monitor_message, options=self._key_options)
            if response['errors']:
                raise Exception(str(response['errors']))
            else:
                monitorId = response['id']

        with self.depl._db:
            self.state = self.UP
            self.api_key = defn.api_key
            self.app_key = defn.app_key
            self.monitor_name = defn.monitor_name
            self.monitor_type = defn.monitor_type
            self.monitor_query = defn.monitor_query
            self.monitor_message = defn.monitor_message
            self.monitor_id = monitorId




    def destroy(self, wipe=False):
        if self.state == self.UP:
            self.log("deleting Datadog monitor ‘{0}’...".format(self.monitor_name))
            self.connect(self.app_key,self.api_key)
            self._dd_api.Monitor.delete(self.monitor_id)

        return True
