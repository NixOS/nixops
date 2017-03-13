import urlparse
import sys
import file

class WrongStateSchemeException(Exception):
    pass

def open(url):
    url = urlparse.urlparse(url)
    scheme = url.scheme

    if scheme == "":
        scheme = "file"

    def raise_(ex):
        raise ex

    switcher = {
        "file": lambda(url): file.StateFile(url.path),
        "etcd": lambda(url): raise_(WrongStateSchemeException("coming soon!")),
    }

    function = switcher.get(scheme, lambda(url): raise_(WrongStateSchemeException("Unknown state scheme!")))
    return function(url)
