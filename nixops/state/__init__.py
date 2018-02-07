import os
import urlparse
import sys
import json_file
import sql_connector

class WrongStateSchemeException(Exception):
    pass

def open(url):
    url_parsed = urlparse.urlparse(url)
    scheme = url_parsed.scheme
    ext = os.path.splitext(url)[1]
    print 'a url {}'.format(url)
    if scheme == "":
        if ext == ".nixops":
            scheme = "sql"
            url = 'sqlite:///' + url
        elif ext == ".json":
            scheme = "json"

    def raise_(ex):
        raise ex

    switcher = {
        "json": lambda(url): json_file.JsonFile(url),
        "sqlite": lambda(url): sql_connector.SQLConnection(url),
        "mysql": lambda(url): sql_connector.SQLConnection(url),
        "sql": lambda(url): sql_connector.SQLConnection(url)
    }

    print 'a url {}'.format(url)
    function = switcher.get(scheme, lambda(url): raise_(WrongStateSchemeException("Unknown state scheme!")))
    return function(url)
