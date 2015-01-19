import os
import sys
import threading
import fcntl


# Allow only one thread to rewrite known_hosts at a time.
lock = threading.Lock()


def remove(ip_address):
    with lock:
        path = os.path.expanduser("~/.ssh/known_hosts")
        if not os.path.isfile(path): return

        with open(os.path.expanduser("~/.ssh/.known_hosts.lock"), 'w') as lockfile:
            fcntl.flock(lockfile, fcntl.LOCK_EX) #unlock is implicit at the end of the with
            f = open(path, 'r')
            contents = f.read()
            f.close()

            new = [ x for x in contents.splitlines() if not (x.startswith(ip_address) and x.endswith('# nixops')) ]

            tmp = "{0}.tmp-{1}".format(path, os.getpid())
            f = open(tmp, 'w')
            f.write('\n'.join(new + [""]))
            f.close()
            os.rename(tmp, path)


def add(ip_address, public_host_key):
    with lock:
        path = os.path.expanduser("~/.ssh/known_hosts")
        if not os.path.isfile(path): return

        with open(os.path.expanduser("~/.ssh/.known_hosts.lock"), 'w') as lockfile:
            fcntl.flock(lockfile, fcntl.LOCK_EX) #unlock is implicit at the end of the with
            f = open(path, 'r')
            contents = f.read()
            f.close()

            new = contents.splitlines()
            new.append('{0} {1} # nixops'.format(ip_address, public_host_key))

            tmp = "{0}.tmp-{1}".format(path, os.getpid())
            f = open(tmp, 'w')
            f.write('\n'.join(new + [""]))
            f.close()
            os.rename(tmp, path)
