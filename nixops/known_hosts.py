import os
import sys
import threading
import fcntl


# Allow only one thread to rewrite known_hosts at a time.
lock = threading.Lock()


def _rewrite(ip_address, add, public_host_key):
    with lock:
        path = os.path.expanduser("~/.ssh/known_hosts")
        if not os.path.isfile(path): return

        with open(os.path.expanduser("~/.ssh/.known_hosts.lock"), 'w') as lockfile:
            fcntl.flock(lockfile, fcntl.LOCK_EX) #unlock is implicit at the end of the with
            f = open(path, 'r')
            contents = f.read()
            f.close()

            def rewrite(l):
                if ' ' not in l: return l
                (first, rest) = l.split(' ', 1)
                names = first.split(',')
                if ip_address not in names: return l
                if not add and public_host_key is not None and public_host_key != rest: return l
                new_names = [ n for n in names  if n != ip_address ]
                return ','.join(new_names) + " " + rest if new_names != [] else None

            new = [ l for l in [ rewrite(l) for l in contents.splitlines() ] if l is not None ]

            if add:
                new.append(ip_address + " " + public_host_key)

            tmp = "{0}.tmp-{1}".format(path, os.getpid())
            f = open(tmp, 'w')
            f.write('\n'.join(new + [""]))
            f.close()
            os.rename(tmp, path)


def remove(ip_address):
    '''Remove any known host key for a given IP address.'''
    _rewrite(ip_address, False, None)


def remove(ip_address, public_host_key):
    '''Remove a specific known host key.'''
    _rewrite(ip_address, False, public_host_key)


def add(ip_address, public_host_key):
    '''Add a known host key.'''
    _rewrite(ip_address, True, public_host_key)
