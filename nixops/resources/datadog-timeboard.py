# -*- coding: utf-8 -*-

import nixops.util
import nixops.resources
import nixops.datadog_utils
import json


class DatadogTimeboardDefinition(nixops.resources.ResourceDefinition):
    """Definition of a Datadog monitor."""

    @classmethod
    def get_type(cls):
        return "datadog-timeboard"

    @classmethod
    def get_resource_type(cls):
        return "datadogTimeboards"

    def __init__(self, xml):
        nixops.resources.ResourceDefinition.__init__(self, xml)
        self.api_key = xml.find("attrs/attr[@name='apiKey']/string").get("value")
        self.app_key = xml.find("attrs/attr[@name='appKey']/string").get("value")
        self.title = xml.find("attrs/attr[@name='title']/string").get("value")
        self.description = xml.find("attrs/attr[@name='description']/string").get("value")
        self.graphs = []
        for graph in xml.findall("attrs/attr[@name='graphs']/list/attrs"):
            graph_entry = {}
            graph_entry['title'] = graph.find("attr[@name='title']/string").get("value")
            graph_entry['definition'] = json.loads(graph.find("attr[@name='definition']/string").get("value"))
            self.graphs.append(graph_entry)
        self.template_variables = []
        tvariables = xml.findall("attrs/attr[@name='templateVariables']/list/attrs")
        for variable in tvariables:
            template_variable = {}
            template_variable['name'] = variable.find("attr[@name='name']/string").get("value")
            prefix = variable.find("attr[@name='prefix']/string")
            template_variable['prefix'] = prefix.get("value") if prefix != None else None
            default = variable.find("attr[@name='default']/string")
            template_variable['default'] = default.get("value") if default != None else None
            self.template_variables.append(template_variable)



    def show_type(self):
        return "{0}".format(self.get_type())

class DatadogTimeboardState(nixops.resources.ResourceState):
    """State of a Datadog monitor"""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    api_key = nixops.util.attr_property("apiKey", None)
    app_key = nixops.util.attr_property("appKey", None)
    title = nixops.util.attr_property("title",None)
    description = nixops.util.attr_property("description",None)
    graphs = nixops.util.attr_property("graphs",[],'json')
    template_variables = nixops.util.attr_property("templateVariables",[],'json')
    timeboard_id = nixops.util.attr_property("timeboardId", None)
    url = nixops.util.attr_property("timeboardURL", None)

    @classmethod
    def get_type(cls):
        return "datadog-timeboard"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._dd_api = None
        self._key_options = None

    def _exists(self):
        return self.state != self.MISSING

    def show_type(self):
        s = super(DatadogTimeboardState, self).show_type()
        return s

    @property
    def resource_id(self):
        return self.title

    def prefix_definition(self, attr):
        return {('resources', 'datadogTimeboards'): attr}

    def get_physical_spec(self):
        return {'url': self.url}

    def get_definition_prefix(self):
        return "resources.datadogTimeboards."

    def connect(self, app_key, api_key):
        if self._dd_api: return
        self._dd_api, self._key_options = nixops.datadog_utils.initializeDatadog(app_key=app_key, api_key=api_key)

    def create_timeboard(self, defn, template_variables):
        response = self._dd_api.Timeboard.create(
            title=defn.title, description=defn.description, graphs=defn.graphs)
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
        self.connect(app_key=defn.app_key, api_key=defn.api_key)
        tv = defn.template_variables
        template_variables = tv if len(tv)>0 else None
        if self.state != self.UP:
            self.log("creating datadog timeboard '{0}...'".format(defn.title))
            timeboard_id, url = self.create_timeboard(defn=defn, template_variables=template_variables)

        if self.state == self.UP:
            if self.timeboard_exist(self.timeboard_id) == False:
                self.warn("datadog timeboard with id {0} doesn't exist anymore.. recreating ...".format(self.monitor_id))
                timeboard_id = self.create_timeboard(defn=defn)
            else:
                response = self._dd_api.Timeboard.update(
                self.timeboard_id, title=defn.title, description=defn.description, graphs=defn.graphs,
                 template_variables=template_variables)
                if 'errors' in response:
                    raise Exception(str(response['errors']))
                else:
                    url = response['url']

        with self.depl._db:
            self.state = self.UP
            self.api_key = defn.api_key
            self.app_key = defn.app_key
            if timeboard_id != None: self.timeboard_id = timeboard_id
            self.title = defn.title
            self.graphs = defn.graphs
            self.template_variables = defn.template_variables
            self.description = defn.description
            self.url = url

    def _destroy(self):
        if self.state == self.UP:
            self.connect(self.app_key,self.api_key)
            if self.timeboard_exist(self.timeboard_id) == False:
                self.warn("datadog timeboard with id {0} already deleted".format(self.timeboard_id))
            else:
                self.log("deleting datadog timeboard ‘{0}’...".format(self.title))
                self._dd_api.Timeboard.delete(self.timeboard_id)

    def destroy(self, wipe=False):
        self._destroy()
        return True
