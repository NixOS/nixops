# -*- coding: utf-8 -*-

import nixops.util
import nixops.resources
import nixops.datadog_utils
import ast


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
        self.extraOptions = {}
        self.extraOptions['thresholds']= {};
        self.monitorName = xml.find("attrs/attr[@name='name']/string").get("value")
        self.monitorType = xml.find("attrs/attr[@name='type']/string").get("value")
        self.monitorQuery = xml.find("attrs/attr[@name='query']/string").get("value")
        self.api_key = xml.find("attrs/attr[@name='api_key']/string").get("value")
        self.app_key = xml.find("attrs/attr[@name='app_key']/string").get("value")
        self.monitorMessage = xml.find("attrs/attr[@name='message']/string").get("value")
        self.setOptionalAttr(xml=xml,name='renotify_interval',type='int')
        self.setOptionalAttr(xml=xml,name='silenced',type='string')
        self.setOptionalAttr(xml=xml,name='escalation_message',type='string')
        self.setOptionalAttr(xml=xml,name='notify_no_data',type='bool')
        self.setOptionalAttr(xml=xml,name='no_data_timeframe',type='int')
        self.setOptionalAttr(xml=xml,name='timeout_h',type='int')
        self.setOptionalAttr(xml=xml,name='require_full_window',type='bool')
        self.setOptionalAttr(xml=xml,name='notify_audit',type='bool')
        self.setOptionalAttr(xml=xml,name='locked',type='bool')
        self.setOptionalAttr(xml=xml,name='include_tags',type='bool')
        for alert in xml.findall("attrs/attr[@name='thresholds']/attrs/attr"):
            if alert.find("int") != None:
                if alert.attrib.get('name') == "ok":
                    self.extraOptions['thresholds']['ok'] = int(alert.find("int").get("value"))
                if alert.attrib.get('name') == "critical":
                    self.extraOptions['thresholds']['critical'] = int(alert.find("int").get("value"))
                if alert.attrib.get('name') == "warning":
                    self.extraOptions['thresholds']['warning'] = int(alert.find("int").get("value"))

    def setOptionalAttr(self,xml,name,type):
        attr = xml.find("attrs/attr[@name='{0}']/{1}".format(name,type))
        if attr != None:
            value = attr.get('value')
            self.extraOptions[name]= ast.literal_eval(value) if name == 'silenced' else value

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

    def create_monitor(self, defn, options):
        response = self._dd_api.Monitor.create(
            type=defn.monitorType, query=defn.monitorQuery, name=defn.monitorName,
            message=defn.monitorMessage, options=options)
        if 'errors' in response:
            raise Exception(str(response['errors']))
        else:
            return response['id']

    def monitor_exist(self, id):
        result = self._dd_api.Monitor.get(id)
        if 'errors' in result:
            return False
        else:
            return True

    def create(self, defn, check, allow_reboot, allow_recreate):
        monitorId = None
        self.connect(app_key=defn.app_key, api_key=defn.api_key)
        options = self._keyOptions
        if self.state != self.UP:
            self.log("creating Datadog monitor '{0}...'".format(defn.monitorName))
            if defn.extraOptions != {}: options.update(defn.extraOptions)
            monitorId = self.create_monitor(defn=defn, options=options)

        if self.state == self.UP:
            if defn.extraOptions != {}: options.update(defn.extraOptions)
            if self.monitor_exist(self.monitorId) == False:
                self.warn("monitor with id {0} doesn't exist anymore.. recreating ...".format(self.monitorId))
                monitorId = self.create_monitor(defn=defn, options=options)
            else:
                response = self._dd_api.Monitor.update(
                self.monitorId, query=defn.monitorQuery, name=defn.monitorName,
                message=defn.monitorMessage, options=options)
                if 'errors' in response:
                    raise Exception(str(response['errors']))

        with self.depl._db:
            self.state = self.UP
            self.api_key = defn.api_key
            self.app_key = defn.app_key
            self.monitorName = defn.monitorName
            self.monitorType = defn.monitorType
            self.monitorQuery = defn.monitorQuery
            self.monitorMessage = defn.monitorMessage
            if monitorId != None: self.monitorId = monitorId





    def destroy(self, wipe=False):
        if self.state == self.UP:
            self.connect(self.app_key,self.api_key)
            if self.monitor_exist(self.monitorId) == False:
                self.warn("monitor with id {0} already deleted".format(self.monitorId))
            else:
                self.log("deleting Datadog monitor ‘{0}’...".format(self.monitorName))
                self._dd_api.Monitor.delete(self.monitorId)

        return True
