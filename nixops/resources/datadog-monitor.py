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
        self.extra_options = {}
        self.extra_options['thresholds']= {};
        self.monitor_name = xml.find("attrs/attr[@name='name']/string").get("value")
        self.monitor_type = xml.find("attrs/attr[@name='type']/string").get("value")
        self.query = xml.find("attrs/attr[@name='query']/string").get("value")
        self.api_key = xml.find("attrs/attr[@name='apiKey']/string").get("value")
        self.app_key = xml.find("attrs/attr[@name='appKey']/string").get("value")
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
                    self.extra_options['thresholds']['ok'] = int(alert.find("int").get("value"))
                if alert.attrib.get('name') == "critical":
                    self.extra_options['thresholds']['critical'] = int(alert.find("int").get("value"))
                if alert.attrib.get('name') == "warning":
                    self.extra_options['thresholds']['warning'] = int(alert.find("int").get("value"))

    def setOptionalAttr(self,xml,name,api_name,type):
        attr = xml.find("attrs/attr[@name='{0}']/{1}".format(name,type))
        if attr != None:
            value = attr.get('value')
            self.extra_options[api_name]= ast.literal_eval(value) if name == 'silenced' else value

    def show_type(self):
        return "{0}".format(self.get_type())

class DatadogMonitorState(nixops.resources.ResourceState):
    """State of a Datadog monitor"""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    api_key = nixops.util.attr_property("apiKey", None)
    app_key = nixops.util.attr_property("appKey", None)
    monitor_name = nixops.util.attr_property("name", None)
    monitor_type = nixops.util.attr_property("type", None)
    query = nixops.util.attr_property("query", None)
    message = nixops.util.attr_property("message", None)
    monitor_id = nixops.util.attr_property("monitorId", None)
    renotify_interval = nixops.util.attr_property("renotify_interval", None)
    silenced =  nixops.util.attr_property("silenced", None)
    escalation_message =  nixops.util.attr_property("escalation_message", None)
    notify_no_data =  nixops.util.attr_property("notify_no_data", None)
    no_data_timeframe =  nixops.util.attr_property("no_data_timeframe", None)
    timeout_h =  nixops.util.attr_property("timeout_h", None)
    require_full_window =  nixops.util.attr_property("require_full_window", None)
    notify_audit =  nixops.util.attr_property("notify_audit", None)
    locked =  nixops.util.attr_property("locked", None)
    include_tags =  nixops.util.attr_property("include_tags", None)
    thresholds_ok =  nixops.util.attr_property("thresholds.ok", None)
    thresholds_warning =  nixops.util.attr_property("thresholds.warning", None)
    thresholds_critical =  nixops.util.attr_property("thresholds.critical", None)

    @classmethod
    def get_type(cls):
        return "datadog-monitor"


    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._dd_api = None
        self._key_options = None

    def _exists(self):
        return self.state != self.MISSING

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

    def create_monitor(self, defn, options):
        response = self._dd_api.Monitor.create(
            type=defn.monitor_type, query=defn.query, name=defn.monitor_name,
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
        monitor_id = None
        self.connect(app_key=defn.app_key, api_key=defn.api_key)
        options = self._key_options
        if self.state != self.UP:
            self.log("creating Datadog monitor '{0}...'".format(defn.monitor_name))
            if defn.extra_options != {}: options.update(defn.extra_options)
            monitor_id = self.create_monitor(defn=defn, options=options)

        if self.state == self.UP:
            if defn.extra_options != {}: options.update(defn.extra_options)
            if self.monitor_exist(self.monitor_id) == False:
                self.warn("monitor with id {0} doesn't exist anymore.. recreating ...".format(self.monitor_id))
                monitor_id = self.create_monitor(defn=defn, options=options)
            else:
                response = self._dd_api.Monitor.update(
                self.monitor_id, query=defn.query, name=defn.monitor_name,
                message=defn.message, options=options)
                if 'errors' in response:
                    raise Exception(str(response['errors']))

        with self.depl._db:
            self.state = self.UP
            self.api_key = defn.api_key
            self.app_key = defn.app_key
            self.monitor_name = defn.monitor_name
            self.monitor_type = defn.monitor_type
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
            if defn.extra_options['thresholds'] != {}:
                thresholds = defn.extra_options['thresholds']
                for k in thresholds:
                    if k=='ok': self.thresholdsOk = thresholds[k]
                    if k=='critical': self.thresholdsCritical = thresholds[k]
                    if k=='warning': self.thresholdsWarning = thresholds[k]
            if monitor_id != None: self.monitor_id = monitor_id

    def getOptionIfExist(self,name,defn):
        if name in defn.extra_options:
            return defn.extra_options[name] if name != 'silenced' else str(defn.extra_options[name])
        else:
            return None



    def destroy(self, wipe=False):
        if self.state == self.UP:
            self.connect(self.app_key,self.api_key)
            if self.monitor_exist(self.monitor_id) == False:
                self.warn("monitor with id {0} already deleted".format(self.monitor_id))
            else:
                self.log("deleting Datadog monitor ‘{0}’...".format(self.monitor_name))
                self._dd_api.Monitor.delete(self.monitor_id)

        return True
