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
        self.query = xml.find("attrs/attr[@name='query']/string").get("value")
        self.apiKey = xml.find("attrs/attr[@name='apiKey']/string").get("value")
        self.appKey = xml.find("attrs/attr[@name='appKey']/string").get("value")
        self.message = xml.find("attrs/attr[@name='message']/string").get("value")
        self.setOptionalAttr(xml=xml, name='renotifyInterval', api_name="renotify_interval", type='int')
        self.setOptionalAttr(xml=xml, name='silenced', api_name='silenced', type='string')
        self.setOptionalAttr(xml=xml, name='escalationMessage', api_name='escalation_message', type='string')
        self.setOptionalAttr(xml=xml, name='notifyNoData', api_name='notify_no_data', type='bool')
        self.setOptionalAttr(xml=xml, name='noDataTimeframe', api_name='no_data_timeframe', type='int')
        self.setOptionalAttr(xml=xml, name='timeoutH', api_name='timeout_h', type='int')
        self.setOptionalAttr(xml=xml, name='requireFullWindow', api_name='require_full_window', type='bool')
        self.setOptionalAttr(xml=xml, name='notifyAudit', api_name='notify_audit', type='bool')
        self.setOptionalAttr(xml=xml, name='locked', api_name='locked', type='bool')
        self.setOptionalAttr(xml=xml, name='includeTags', api_name='include_tags', type='bool')
        for alert in xml.findall("attrs/attr[@name='thresholds']/attrs/attr"):
            if alert.find("int") != None:
                if alert.attrib.get('name') == "ok":
                    self.extraOptions['thresholds']['ok'] = int(alert.find("int").get("value"))
                if alert.attrib.get('name') == "critical":
                    self.extraOptions['thresholds']['critical'] = int(alert.find("int").get("value"))
                if alert.attrib.get('name') == "warning":
                    self.extraOptions['thresholds']['warning'] = int(alert.find("int").get("value"))

    def setOptionalAttr(self,xml,name,api_name,type):
        attr = xml.find("attrs/attr[@name='{0}']/{1}".format(name,type))
        if attr != None:
            value = attr.get('value')
            self.extraOptions[api_name]= ast.literal_eval(value) if name == 'silenced' else value

    def show_type(self):
        return "{0}".format(self.get_type())

class DatadogMonitorState(nixops.resources.ResourceState):
    """State of a Datadog monitor"""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    apiKey = nixops.util.attr_property("apiKey", None)
    appKey = nixops.util.attr_property("appKey", None)
    monitorName = nixops.util.attr_property("name", None)
    monitorType = nixops.util.attr_property("type", None)
    query = nixops.util.attr_property("query", None)
    message = nixops.util.attr_property("message", None)
    monitorId = nixops.util.attr_property("monitorId", None)
    renotifyInterval = nixops.util.attr_property("renotifyInterval", None)
    silenced =  nixops.util.attr_property("silenced", None)
    escalationMessage =  nixops.util.attr_property("escalationMessage", None)
    notifyNoData =  nixops.util.attr_property("notifyNoData", None)
    noDataTimeframe =  nixops.util.attr_property("noDataTimeframe", None)
    timeoutH =  nixops.util.attr_property("timeoutH", None)
    requireFullWindow =  nixops.util.attr_property("requireFullWindow", None)
    notifyAudit =  nixops.util.attr_property("notifyAudit", None)
    locked =  nixops.util.attr_property("locked", None)
    includeTags =  nixops.util.attr_property("include_tags", None)
    thresholdsOk =  nixops.util.attr_property("thresholds.ok", None)
    thresholdsWarning =  nixops.util.attr_property("thresholds.warning", None)
    thresholdsCritical =  nixops.util.attr_property("thresholds.critical", None)

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

    def connect(self, appKey, apiKey):
        if self._dd_api: return
        self._dd_api, self._keyOptions = nixops.datadog_utils.initializeDatadog(appKey=appKey, apiKey=apiKey)

    def create_monitor(self, defn, options):
        response = self._dd_api.Monitor.create(
            type=defn.monitorType, query=defn.query, name=defn.monitorName,
            message=defn.message, options=options)
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
        self.connect(appKey=defn.appKey, apiKey=defn.apiKey)
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
                self.monitorId, query=defn.query, name=defn.monitorName,
                message=defn.message, options=options)
                if 'errors' in response:
                    raise Exception(str(response['errors']))

        with self.depl._db:
            self.state = self.UP
            self.apiKey = defn.apiKey
            self.appKey = defn.appKey
            self.monitorName = defn.monitorName
            self.monitorType = defn.monitorType
            self.query = defn.query
            self.message = defn.message
            self.renotifyInterval = self.getOptionIfExist(name='renotify_interval',defn=defn)
            self.silenced = self.getOptionIfExist(name='silenced',defn=defn)
            self.escalationMessage = self.getOptionIfExist(name='escalation_message',defn=defn)
            self.notifyNoData = self.getOptionIfExist(name='notify_no_data',defn=defn)
            self.noDataTimeframe = self.getOptionIfExist(name='no_data_timeframe',defn=defn)
            self.timeoutH = self.getOptionIfExist(name='timeout_h',defn=defn)
            self.requireFullWindow = self.getOptionIfExist(name='require_full_window',defn=defn)
            self.notifyAudit = self.getOptionIfExist(name='notify_audit',defn=defn)
            self.locked = self.getOptionIfExist(name='locked',defn=defn)
            self.includeTags = self.getOptionIfExist(name='include_tags',defn=defn)
            if defn.extraOptions['thresholds'] != {}:
                thresholds = defn.extraOptions['thresholds']
                for k in thresholds:
                    if k=='ok': self.thresholdsOk = thresholds[k]
                    if k=='critical': self.thresholdsCritical = thresholds[k]
                    if k=='warning': self.thresholdsWarning = thresholds[k]
            if monitorId != None: self.monitorId = monitorId

    def getOptionIfExist(self,name,defn):
        if name in defn.extraOptions:
            return defn.extraOptions[name] if name != 'silenced' else str(defn.extraOptions[name])
        else:
            return None



    def destroy(self, wipe=False):
        if self.state == self.UP:
            self.connect(self.appKey,self.apiKey)
            if self.monitor_exist(self.monitorId) == False:
                self.warn("monitor with id {0} already deleted".format(self.monitorId))
            else:
                self.log("deleting Datadog monitor ‘{0}’...".format(self.monitorName))
                self._dd_api.Monitor.delete(self.monitorId)

        return True
