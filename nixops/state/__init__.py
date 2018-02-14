import os
import urlparse
import sys
import json_file
import sqlite_connector

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
