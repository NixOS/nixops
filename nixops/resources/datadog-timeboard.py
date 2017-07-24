# -*- coding: utf-8 -*-

import nixops.util
import nixops.resources
import nixops.datadog_utils
import json


class DatadogTimeboardDefinition(nixops.resources.ResourceDefinition):
    """Definition of a Datadog timeboard."""

    @classmethod
    def get_type(cls):
        return "datadog-timeboard"

    @classmethod
    def get_resource_type(cls):
        return "datadogTimeboards"

    def show_type(self):
        return "{0}".format(self.get_type())

class DatadogTimeboardState(nixops.resources.ResourceState):
    """State of a Datadog timeboard"""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    api_key = nixops.util.attr_property("apiKey", None)
    app_key = nixops.util.attr_property("appKey", None)
    title = nixops.util.attr_property("title",None)
    description = nixops.util.attr_property("description",None)
    graphs = nixops.util.attr_property("graphs",[],'json')
    template_variables = nixops.util.attr_property("templateVariables",[],'json')
    timeboard_id = nixops.util.attr_property("timeboardId", None)
    url = nixops.util.attr_property("timeboardURL", None)
    read_only = nixops.util.attr_property("readOnly",None)

    @classmethod
    def get_type(cls):
        return "datadog-timeboard"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._dd_api = None
        self._key_options = None
        self._dash_url = nixops.datadog_utils.get_base_url()+"dash/"

    def show_type(self):
        s = super(DatadogTimeboardState, self).show_type()
        return s

    @property
    def resource_id(self):
        return self._dash_url + self.timeboard_id if self.timeboard_id else None

    def prefix_definition(self, attr):
        return {('resources', 'datadogTimeboards'): attr}

    def get_physical_spec(self):
        return {'url': self._dash_url + self.timeboard_id } if self.timeboard_id else {} 

    def get_definition_prefix(self):
        return "resources.datadogTimeboards."

    def connect(self, app_key, api_key):
        if self._dd_api: return
        self._dd_api, self._key_options = nixops.datadog_utils.initializeDatadog(app_key=app_key, api_key=api_key)

    def create_timeboard(self, defn, graphs, template_variables, read_only):
        response = self._dd_api.Timeboard.create(
            title=defn.config['title'], description=defn.config['description'], graphs=graphs,
             template_variables=template_variables, read_only=read_only)
        if 'errors' in response:
            raise Exception(str(response['errors']))
        else:
            return response['dash']['id'], response['url']

    def timeboard_exist(self, id):
        result = self._dd_api.Timeboard.get(id)
        if 'errors' in result:
            return False
        else:
            return True

    def create(self, defn, check, allow_reboot, allow_recreate):
        timeboard_id = None
        url = None
        self.connect(app_key=defn.config['appKey'], api_key=defn.config['apiKey'])
        template_variables = nixops.datadog_utils.get_template_variables(defn=defn)
        read_only = True if defn.config['readOnly']=="true" else False
        graphs = []
        for g in defn.config['graphs']:
            graph = {}
            graph['title'] = g['title']
            graph['definition'] = json.loads(g['definition'])
            graphs.append(graph)

        if self.state != self.UP:
            self.log("creating datadog timeboard '{0}...'".format(defn.config['title']))
            timeboard_id, url = self.create_timeboard(defn=defn, graphs=graphs, template_variables=template_variables, read_only=read_only)

        if self.state == self.UP:
            if self.timeboard_exist(self.timeboard_id) == False:
                self.warn("datadog timeboard with id {0} doesn't exist anymore.. recreating ...".format(self.timeboard_id))
                timeboard_id, url = self.create_timeboard(defn=defn, graphs=graphs, template_variables=template_variables, read_only=read_only)
            else:
                response = self._dd_api.Timeboard.update(
                self.timeboard_id, title=defn.config['title'], description=defn.config['description'], graphs=graphs,
                 template_variables=template_variables, read_only=read_only)
                if 'errors' in response:
                    raise Exception(str(response['errors']))
                else:
                    url = response['url']

        with self.depl._state.db:
            self.state = self.UP
            self.api_key = defn.config['apiKey']
            self.app_key = defn.config['appKey']
            if timeboard_id != None: self.timeboard_id = timeboard_id
            self.title = defn.config['title']
            self.graphs = graphs
            self.template_variables = template_variables
            self.description = defn.config['description']
            self.url = url
            self.read_only = read_only

    def _destroy(self):
        if self.state == self.UP:
            self.connect(self.app_key,self.api_key)
            if self.timeboard_exist(self.timeboard_id) == False:
                self.warn("datadog timeboard with id {0} already deleted".format(self.timeboard_id))
            else:
                self.log("deleting datadog timeboard ‘{0}’...".format(self.title))
                response = self._dd_api.Timeboard.delete(self.timeboard_id)
                if 'errors' in response.keys():
                    raise Exception("there was errors while deleting the timeboard: {}".format(
                        str(response['errors'])))

    def destroy(self, wipe=False):
        self._destroy()
        return True
