# -*- coding: utf-8 -*-

import nixops.util
import nixops.resources
import nixops.datadog_utils


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
        for graph in xml.findall("attrs/attr[@name='subscriptions']/list/attrs")
            graph['title'] =


    def show_type(self):
        return "{0}".format(self.get_type())

class DatadogTimeboardState(nixops.resources.ResourceState):
    """State of a Datadog monitor"""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    api_key = nixops.util.attr_property("apiKey", None)
    app_key = nixops.util.attr_property("appKey", None)

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

    def get_definition_prefix(self):
        return "resources.datadogTimeboards."

    def connect(self, app_key, api_key):
        if self._dd_api: return
        self._dd_api, self._key_options = nixops.datadog_utils.initializeDatadog(app_key=app_key, api_key=api_key)

    def create_timeboard(self, defn, options):

    def timeboard_exist(self, id):

    def create(self, defn, check, allow_reboot, allow_recreate):

    def destroy(self, wipe=False):
        self._destroy()
        return True
