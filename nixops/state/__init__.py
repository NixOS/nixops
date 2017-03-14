import urlparse
import sys
import sqlite3_file

class WrongStateSchemeException(Exception):
    pass

def open(url):
    url = urlparse.urlparse(url)
    scheme = url.scheme

    if scheme == "":
        scheme = "sqlite3"

    def raise_(ex):
        raise ex

    switcher = {
        "sqlite3": lambda(url): sqlite3_file.StateFile(url.path),
    }

    function = switcher.get(scheme, lambda(url): raise_(WrongStateSchemeException("Unknown state scheme!")))
    return function(url)
