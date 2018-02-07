import os
import urlparse
import sys
import json_file
import sql_connector

class WrongStateSchemeException(Exception):
    pass

def open(url):
    url = urlparse.urlparse(url)
    scheme = url.scheme
    ext = os.path.splitext(url.path)[1]

    if scheme == "":
        if ext == ".nixops":
            scheme = "sql"
            url = 'sqlite:///' + url.path
        elif ext == ".json":
            scheme = "json"

    def raise_(ex):
        raise ex

    switcher = {
        "json": lambda(url): json_file.JsonFile(url.path),
        "sql": lambda(url): sql_connector.SQLConnection(url),
    }

    function = switcher.get(scheme, lambda(url): raise_(WrongStateSchemeException("Unknown state scheme!")))
    return function(url)
