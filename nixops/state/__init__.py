import os
import urlparse
import sys
import json_file
import sql_connector
import sqlite_connector

class WrongStateSchemeException(Exception):
    pass

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
        "mysql": lambda(url): sql_connector.SQLConnection(url),
        "sqlite": lambda(url): sqlite_connector.SQLiteConnection(url)
    }

    function = switcher.get(scheme, lambda(url): raise_(WrongStateSchemeException("Unknown state scheme! {}".format(url))))
    return function(url)
