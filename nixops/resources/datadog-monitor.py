# -*- coding: utf-8 -*-

import nixops.util
import nixops.resources
import nixops.datadog_utils
import json
import ast


class DatadogMonitorDefinition(nixops.resources.ResourceDefinition):
    """Definition of a Datadog monitor."""

    @classmethod
    def get_type(cls):
        return "datadog-monitor"

    @classmethod
    def get_resource_type(cls):
        return "datadogMonitors"

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
    options = nixops.util.attr_property("monitorOptions",[],'json')
    tags = nixops.util.attr_property("monitorTags", None, 'json')

    @classmethod
    def get_type(cls):
        return "datadog-monitor"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._dd_api = None
        self._key_options = None
        self._monitor_url = nixops.datadog_utils.get_base_url()+"monitors#"

    def _exists(self):
        return self.state != self.MISSING

    def show_type(self):
        s = super(DatadogMonitorState, self).show_type()
        return s

    @property
    def resource_id(self):
        return self._monitor_url + self.monitor_id if self.monitor_id else None

    def get_definition_prefix(self):
        return "resources.datadogMonitors."

    def get_physical_spec(self):
        return {'url': self._monitor_url + self.monitor_id } if self.monitor_id else {}

    def prefix_definition(self, attr):
        return {('resources', 'datadogMonitors'): attr}

    def connect(self, app_key, api_key):
        if self._dd_api: return
        self._dd_api, self._key_options = nixops.datadog_utils.initializeDatadog(app_key=app_key, api_key=api_key)

    def create_monitor(self, defn, options):
        response = self._dd_api.Monitor.create(
            type=defn.config['type'], query=defn.config['query'], name=defn.config['name'],
            message=defn.config['message'], options=options, tags=defn.config['monitorTags'])
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
        self.connect(app_key=defn.config['appKey'], api_key=defn.config['apiKey'])
        options = json.loads(defn.config['monitorOptions'])
        silenced = defn.config['silenced']
        if silenced!=None: options['silenced'] = ast.literal_eval(silenced)
        options.update(self._key_options)
        if self.state != self.UP:
            self.log("creating datadog monitor '{0}...'".format(defn.config['name']))
            monitor_id = self.create_monitor(defn=defn, options=options)

        if self.state == self.UP:
            if self.monitor_exist(self.monitor_id) == False:
                self.warn("monitor with id {0} doesn't exist anymore.. recreating ...".format(self.monitor_id))
                monitor_id = self.create_monitor(defn=defn, options=options)
            else:
                self.log("updating datadog monitor '{0}...'".format(defn.config['name']))
                response = self._dd_api.Monitor.update(
                self.monitor_id, query=defn.config['query'], name=defn.config['name'],
                message=defn.config['message'], options=options, tags=defn.config['monitorTags'])
                if 'errors' in response:
                    raise Exception(str(response['errors']))

        with self.depl._db:
            self.state = self.UP
            self.api_key = defn.config['apiKey']
            self.app_key = defn.config['appKey']
            self.monitor_name = defn.config['name']
            self.monitor_type = defn.config['type']
            self.query = defn.config['query']
            self.message = defn.config['message']
            self.options = defn.config['monitorOptions']
            self.tags = defn.config['monitorTags']
            if monitor_id != None: self.monitor_id = monitor_id

    def destroy(self, wipe=False):
        if self.state == self.UP:
            self.connect(self.app_key,self.api_key)
            if self.monitor_exist(self.monitor_id) == False:
                self.warn("datadog monitor with id {0} already deleted".format(self.monitor_id))
            else:
                self.log("deleting datadog monitor ‘{0}’...".format(self.monitor_name))
                response = self._dd_api.Monitor.delete(self.monitor_id)
                if 'errors' in response.keys():
                    raise Exception("there was errors while deleting the monitor: {}".format(
                        str(response['errors'])))
        return True
