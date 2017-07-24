# -*- coding: utf-8 -*-

import nixops.util
import nixops.resources
import nixops.datadog_utils
import json


class DatadogScreenboardDefinition(nixops.resources.ResourceDefinition):
    """Definition of a Datadog screenboard."""

    @classmethod
    def get_type(cls):
        return "datadog-screenboard"

    @classmethod
    def get_resource_type(cls):
        return "datadogScreenboards"

    def show_type(self):
        return "{0}".format(self.get_type())

class DatadogScreenboardState(nixops.resources.ResourceState):
    """State of a Datadog screenboard"""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    api_key = nixops.util.attr_property("apiKey", None)
    app_key = nixops.util.attr_property("appKey", None)
    board_title = nixops.util.attr_property("boardTitle",None)
    description = nixops.util.attr_property("description",None)
    width = nixops.util.attr_property("width",None)
    height = nixops.util.attr_property("height",None)
    widgets= nixops.util.attr_property("widgets",[],'json')
    template_variables = nixops.util.attr_property("templateVariables",[],'json')
    screenboard_id = nixops.util.attr_property("screenboardId", None)
    read_only = nixops.util.attr_property("readOnly",None)

    @classmethod
    def get_type(cls):
        return "datadog-screenboard"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._dd_api = None
        self._key_options = None
        self._screen_url = nixops.datadog_utils.get_base_url()+"screen/"

    def show_type(self):
        s = super(DatadogScreenboardState, self).show_type()
        return s

    @property
    def resource_id(self):
        return self._screen_url + self.screenboard_id if self.screenboard_id else None

    def get_physical_spec(self):
        return {'url': self._screen_url + self.screenboard_id } if self.screenboard_id else {} 

    def prefix_definition(self, attr):
        return {('resources', 'datadogScreenboards'): attr}

    def get_definition_prefix(self):
        return "resources.datadogScreenboards."

    def connect(self, app_key, api_key):
        if self._dd_api: return
        self._dd_api, self._key_options = nixops.datadog_utils.initializeDatadog(app_key=app_key, api_key=api_key)

    def create_screenboard(self, defn, widgets, template_variables, read_only):
        response = self._dd_api.Screenboard.create(
            board_title=defn.config["boardTitle"], description=defn.config['description'], widgets=widgets,
             template_variables=template_variables, width=defn.config['width'], height=defn.config['height'], read_only=read_only)
        if 'errors' in response:
            raise Exception(str(response['errors']))
        else:
            return response['id']

    def screenboard_exist(self, id):
        result = self._dd_api.Screenboard.get(id)
        if 'errors' in result:
            return False
        else:
            return True

    def create(self, defn, check, allow_reboot, allow_recreate):
        screenboard_id = None
        self.connect(app_key=defn.config['appKey'], api_key=defn.config['apiKey'])
        template_variables = nixops.datadog_utils.get_template_variables(defn=defn)
        read_only = True if defn.config['readOnly']=="true" else False
        widgets = []
        for widget in defn.config['widgets']:
            widgets.append(json.loads(widget))
        if self.state != self.UP:
            self.log("creating datadog screenboard '{0}...'".format(defn.config['boardTitle']))
            screenboard_id = self.create_screenboard(defn=defn, widgets=widgets, template_variables=template_variables, read_only=read_only)
        if self.state == self.UP:
            if self.screenboard_exist(self.screenboard_id) == False:
                self.warn("datadog screenboard with id {0} doesn't exist anymore.. recreating ...".format(self.screenboard_id))
                screenboard_id = self.create_screenboard(defn=defn, widgets=widgets, template_variables=template_variables, read_only=read_only)
            else:
                response = self._dd_api.Screenboard.update(
                self.screenboard_id, board_title=defn.config['boardTitle'], description=defn.config['description'], widgets=widgets,
                 template_variables=template_variables, width=defn.config['width'], height=defn.config['height'], read_only=read_only)
                if 'errors' in response:
                    raise Exception(str(response['errors']))

        with self.depl._state.db:
            self.state = self.UP
            self.api_key = defn.config['apiKey']
            self.app_key = defn.config['appKey']
            if screenboard_id != None: self.screenboard_id = screenboard_id
            self.board_title = defn.config['boardTitle']
            self.widgets = widgets
            self.template_variables = defn.config['templateVariables']
            self.description = defn.config['description']
            self.read_only = read_only

    def _destroy(self):
        if self.state == self.UP:
            self.connect(self.app_key,self.api_key)
            if self.screenboard_exist(self.screenboard_id) == False:
                self.warn("datadog screenboard with id {0} already deleted".format(self.screenboard_id))
            else:
                self.log("deleting datadog screenboard ‘{0}’...".format(self.board_title))
                response = self._dd_api.Screenboard.delete(self.screenboard_id)
                if 'errors' in response.keys():
                    raise Exception("there was errors while deleting the screenboard: {}".format(
                        str(response['errors'])))
    def destroy(self, wipe=False):
        self._destroy()
        return True
