import os
import threading
import fcntl

from typing import Optional

# Allow only one thread to rewrite known_hosts at a time.
LOCK = threading.Lock()


def _rewrite(ip_address: str, add_ip: bool, public_host_key: str) -> None:
    with LOCK:
        path = os.path.expanduser("~/.ssh/known_hosts")

        # If hosts file doesn't exist, create an empty file
        if not os.path.isfile(path):
            basedir = os.path.dirname(path)
            if not os.path.exists(basedir):
                os.makedirs(basedir)
            open(path, "a").close()

        with open(os.path.expanduser("~/.ssh/.known_hosts.lock"), "w") as lockfile:
            fcntl.flock(
                lockfile, fcntl.LOCK_EX
            )  # unlock is implicit at the end of the with
            with open(path, "r") as f:
                contents = f.read()

            def rewrite(lst: str) -> Optional[str]:
                if " " not in lst:
                    return lst
                (first, rest) = lst.split(" ", 1)
                names = first.split(",")
                if ip_address not in names:
                    return lst
                if not add_ip and public_host_key != rest:
                    return lst
                new_names = [n for n in names if n != ip_address]
                return ",".join(new_names) + " " + rest if new_names != [] else None

            new = [
                line
                for line in [rewrite(line) for line in contents.splitlines()]
                if line is not None
            ]

            if add_ip:
                new.append(ip_address + " " + public_host_key)

            tmp = "{0}.tmp-{1}".format(path, os.getpid())
            f = open(tmp, "w")
            f.write("\n".join(new + [""]))
            f.close()
            os.rename(tmp, path)


def remove(ip_address: str, public_host_key: str) -> None:
    """Remove a specific known host key."""
    _rewrite(ip_address, False, public_host_key)


def add(ip_address: str, public_host_key: str) -> None:
    """Add a known host key."""
    _rewrite(ip_address, True, public_host_key)


def update(prev_address: str, new_address: str, public_host_key: str) -> None:
    # FIXME: this rewrites known_hosts twice.
    if prev_address != new_address:
        remove(prev_address, public_host_key)
    add(new_address, public_host_key)
