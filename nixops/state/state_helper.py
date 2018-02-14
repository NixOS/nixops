import json
import collections
import nixops.util


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
        self._state.set_resource_attrs(self.uuid, self.id, {key:value})

    def __getitem__(self, key):
        value = self._state.get_resource_attr(self.uuid, self.id, name)
        try:
            return json.loads(value)
        except ValueError:
            return value
        raise KeyError("couldn't find key {} in the state file".format(key))

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
