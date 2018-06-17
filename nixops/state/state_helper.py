# -*- coding: utf-8 -*-

import json
import collections
import nixops.util


def _subclasses(cls):
    sub = cls.__subclasses__()
    return [cls] if not sub else [g for s in sub for g in _subclasses(s)]

def _create_resource_state(depl, type, name, id):
    """Create a resource state object  of the desired type."""
    for cls in _subclasses(nixops.resources.ResourceState):
        if type == cls.get_type():
            return cls(depl, name, id)
    raise nixops.deployment.UnknownBackend("unknown resource type ‘{}’".format(type))

class StateDict(collections.MutableMapping):
    """
       An implementation of a MutableMapping container providing
       a python dict like behavior for the NixOps state file.
    """
    # TODO implement __repr__ for convenience e.g debuging the structure
    def __init__(self, depl, id):
        super(StateDict, self).__init__()
        self._state = depl._state
        self.uuid = depl.uuid
        self.id = id

    def __setitem__(self, key, value):
        value_ = value

        if not isinstance(value, basestring):
            value_ = json.dumps(value)

        self._state.set_resource_attrs(self.uuid, self.id, { key: value_ })

    def __getitem__(self, key):
        value = self._state.get_resource_attr(self.uuid, self.id, key)

        if value == nixops.util.undefined:
            raise KeyError("couldn't find key {} in the state file".format(key))

        if isinstance(value, basestring):
            try:
                return json.loads(value)
            except ValueError:
                return value

        return value


    def __delitem__(self, key):
        self._state.del_resource_attr(self.uuid, self.id, key)

    def keys(self):
        # Generally the list of keys per ResourceAttrs is relatively small
        # so this should be also relatively fast.
        attrs = self._state.get_all_resource_attrs(self.uuid, self.id)
        return [key for key,value in attrs.iteritems()]

    def __iter__(self):
        return iter(self.keys())

    def __len__(self):
        return len(self.keys())
