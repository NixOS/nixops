import os
import sys
import threading


# Allow only one thread to rewrite known_hosts at a time.  TODO: use a
# file lock.
lock = threading.Lock()


def _rewrite(ip_address, public_host_key):
    with lock:
        path = os.path.expanduser("~/.ssh/known_hosts")
        if not os.path.isfile(path): return
    
        f = open(path, 'r')
        contents = f.read()
        f.close()

        def rewrite(l):
            (names, rest) = l.split(' ', 1)
            new_names = [ n for n in names.split(',') if n != ip_address ]
            return ','.join(new_names) + " " + rest if new_names != [] else None

        new = [ l for l in [ rewrite(l) for l in contents.splitlines() ] if l is not None ]

        if public_host_key:
            new.append(ip_address + " " + public_host_key)

        tmp = "{0}.tmp-{1}".format(path, os.getpid())
        f = open(tmp, 'w')
        f.write('\n'.join(new + [""]))
        f.close()
        os.rename(tmp, path)


def remove(ip_address):
    _rewrite(ip_address, None)


def add(ip_address, public_host_key):
    _rewrite(ip_address, public_host_key)
