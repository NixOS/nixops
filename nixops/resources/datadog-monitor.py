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
        self.thresholds = {}
        self.monitorName = xml.find("attrs/attr[@name='name']/string").get("value")
        self.monitorType = xml.find("attrs/attr[@name='type']/string").get("value")
        self.monitorQuery = xml.find("attrs/attr[@name='query']/string").get("value")
        self.api_key = xml.find("attrs/attr[@name='api_key']/string").get("value")
        self.app_key = xml.find("attrs/attr[@name='app_key']/string").get("value")
        self.monitorMessage =  xml.find("attrs/attr[@name='message']/string").get("value")
        for alert in xml.findall("attrs/attr[@name='thresholds']/attrs/attr"):
            if alert.attrib.get('name') == "ok":
                self.thresholds['ok'] = int(alert.find("int").get("value"))
            if alert.attrib.get('name') == "critical":
                self.thresholds['critical'] = int(alert.find("int").get("value"))
            if alert.attrib.get('name') == "warning":
                self.thresholds['warning'] = int(alert.find("int").get("value"))

    def show_type(self):
        return "{0}".format(self.get_type())

class DatadogMonitorState(nixops.resources.ResourceState):
    """State of a Datadog monitor"""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    api_key = nixops.util.attr_property("api_key", None)
    app_key = nixops.util.attr_property("app_key", None)
    monitorName = nixops.util.attr_property("monitor_name", None)
    monitorType = nixops.util.attr_property("monitor_type", None)
    monitorQuery = nixops.util.attr_property("monitor_query", None)
    monitorMessage = nixops.util.attr_property("monitor_message", None)
    monitorId = nixops.util.attr_property("monitor_id", None)

    @classmethod
    def get_type(cls):
        return "datadog-monitor"


    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._dd_api = None
        self._keyOptions = None

    def _exists(self):
        return self.state != self.MISSING

    def show_type(self):
        s = super(DatadogMonitorState, self).show_type()
        return s


    @property
    def resource_id(self):
        return self.monitorName


    def get_definition_prefix(self):
        return "resources.datadogMonitors."

    def connect(self, app_key, api_key):
        if self._dd_api: return
        self._dd_api, self._keyOptions = nixops.datadog_utils.initializeDatadog(app_key=app_key, api_key=api_key)

    def create(self, defn, check, allow_reboot, allow_recreate):
        if check or self.state != self.UP:
            self.connect(app_key=defn.app_key, api_key=defn.api_key)
            if self.monitorId != None:
                self._dd_api.Monitor.delete(self.monitorId)
            self.log("creating Datadog monitor '{0}...'".format(defn.monitorName))
            options = self._keyOptions
            if defn.thresholds != {}: options.update(defn.thresholds)
            response = self._dd_api.Monitor.create(
                type=defn.monitorType, query=defn.monitorQuery, name=defn.monitorName,
                message=defn.monitorMessage, options=options)
            if 'errors' in response:
                raise Exception(str(response['errors']))
            else:
                monitorId = response['id']

        with self.depl._db:
            self.state = self.UP
            self.api_key = defn.api_key
            self.app_key = defn.app_key
            self.monitorName = defn.monitorName
            self.monitorType = defn.monitorType
            self.monitorQuery = defn.monitorQuery
            self.monitorMessage = defn.monitorMessage
            self.monitorId = monitorId




    def destroy(self, wipe=False):
        if self.state == self.UP:
            self.log("deleting Datadog monitor ‘{0}’...".format(self.monitorName))
            self.connect(self.app_key,self.api_key)
            self._dd_api.Monitor.delete(self.monitorId)

        return True
