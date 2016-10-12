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

    def __init__(self, xml):
        nixops.resources.ResourceDefinition.__init__(self, xml)
        self.api_key = xml.find("attrs/attr[@name='apiKey']/string").get("value")
        self.app_key = xml.find("attrs/attr[@name='appKey']/string").get("value")
        self.board_title = xml.find("attrs/attr[@name='boardTitle']/string").get("value")
        description = xml.find("attrs/attr[@name='description']/string").get("value")
        self.description = description if description != "" else None
        self.widgets = []
        for widget in xml.findall("attrs/attr[@name='widgets']/list"):
            widget_entry = json.loads(widget.find("string").get("value"))
            self.widgets.append(widget_entry)
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
        width = xml.find("attrs/attr[@name='width']/int")
        self.width = width.get('value') if width != None else None
        height = xml.find("attrs/attr[@name='height']/int")
        self.height = height.get('value') if height != None else None
        read_only = xml.find("attrs/attr[@name='readOnly']/bool").get("value")
        self.read_only = True if read_only=="true" else False

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

    def show_type(self):
        s = super(DatadogScreenboardState, self).show_type()
        return s

    @property
    def resource_id(self):
        return self.board_title

    def get_definition_prefix(self):
        return "resources.datadogScreenboards."

    def connect(self, app_key, api_key):
        if self._dd_api: return
        self._dd_api, self._key_options = nixops.datadog_utils.initializeDatadog(app_key=app_key, api_key=api_key)

    def create_screenboard(self, defn, template_variables):
        response = self._dd_api.Screenboard.create(
            board_title=defn.board_title, description=defn.description, widgets=defn.widgets,
             template_variables=template_variables, width=defn.width, height=defn.height, read_only=defn.read_only)
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
        self.connect(app_key=defn.app_key, api_key=defn.api_key)
        tv = defn.template_variables
        template_variables = tv if len(tv)>0 else None
        if self.state != self.UP:
            self.log("creating datadog screenboard '{0}...'".format(defn.board_title))
            screenboard_id = self.create_screenboard(defn=defn, template_variables=template_variables)
        if self.state == self.UP:
            if self.screenboard_exist(self.screenboard_id) == False:
                self.warn("datadog screenboard with id {0} doesn't exist anymore.. recreating ...".format(self.screenboard_id))
                screenboard_id = self.create_screenboard(defn=defn, template_variables=template_variables)
            else:
                response = self._dd_api.Screenboard.update(
                self.screenboard_id, board_title=defn.board_title, description=defn.description, widgets=defn.widgets,
                 template_variables=template_variables, width=defn.width, height=defn.height, read_only=defn.read_only)
                if 'errors' in response:
                    raise Exception(str(response['errors']))

        with self.depl._db:
            self.state = self.UP
            self.api_key = defn.api_key
            self.app_key = defn.app_key
            if screenboard_id != None: self.screenboard_id = screenboard_id
            self.board_title = defn.board_title
            self.widgets = defn.widgets
            self.template_variables = defn.template_variables
            self.description = defn.description
            self.read_only = defn.read_only

    def _destroy(self):
        if self.state == self.UP:
            self.connect(self.app_key,self.api_key)
            if self.screenboard_exist(self.screenboard_id) == False:
                self.warn("datadog screenboard with id {0} already deleted".format(self.screenboard_id))
            else:
                self.log("deleting datadog screenboard ‘{0}’...".format(self.board_title))
                self._dd_api.Screenboard.delete(self.screenboard_id)

    def destroy(self, wipe=False):
        self._destroy()
        return True