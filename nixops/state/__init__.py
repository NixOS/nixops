import os
import urlparse
import sys
import json_file
import sqlite_connector
import json
import collections
import nixops.util

class WrongStateSchemeException(Exception):
    pass


def get_default_state_file():
    home = os.environ.get("HOME", "") + "/.nixops"
    if not os.path.exists(home):
        old_home = os.environ.get("HOME", "") + "/.charon"
        if os.path.exists(old_home):
            sys.stderr.write("renaming {!r} to {!r}...\n".format(old_home, home))
            os.rename(old_home, home)
            if os.path.exists(home + "/deployments.charon"):
                os.rename(home + "/deployments.charon", home + "/deployments.nixops")
        else:
            os.makedirs(home, 0700)
    return os.environ.get("NIXOPS_STATE", os.environ.get("CHARON_STATE", home + "/deployments.nixops"))


def open(url):
    print 'url = {}'.format(url)
    url_parsed = urlparse.urlparse(url)
    scheme = url_parsed.scheme
    ext = os.path.splitext(url)[1]
    if scheme == "":
        if ext == ".nixops":
            scheme = "sqlite"
            url = 'sqlite://' + url
        elif ext == ".json":
            scheme = "json"

    def raise_(ex):
        raise ex

    switcher = {
        "json": lambda(url): json_file.JsonFile(url),
        "sqlite": lambda(url): sqlite_connector.SQLiteConnection(url)
    }

    function = switcher.get(scheme, lambda(url): raise_(WrongStateSchemeException("Unknown state scheme! {}".format(url))))
    return function(url)


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
