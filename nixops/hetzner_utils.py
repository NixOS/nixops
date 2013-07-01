import time
import json
import socket

from datetime import datetime
from functools import partial
from base64 import b64encode
from urllib import urlencode
from httplib import HTTPSConnection, BadStatusLine

ROBOT_HOST = "robot-ws.your-server.de"


class RobotError(Exception):
    pass


class ManualReboot(Exception):
    pass


class ConnectError(Exception):
    pass


class RobotConnection(object):
    def __init__(self, user, passwd):
        self.user = user
        self.passwd = passwd
        self.conn = HTTPSConnection(ROBOT_HOST)

    def _request(self, method, path, data, headers, retry=1):
        self.conn.request(method.upper(), path, data, headers)
        try:
            return self.conn.getresponse()
        except BadStatusLine:
            # XXX: Sometimes, the API server seems to have a problem with
            # keepalives.
            if retry <= 0:
                raise

            self.conn.close()
            self.conn.connect()
            return self._request(method, path, data, headers, retry - 1)

    def request(self, method, path, data=None):
        if data is not None:
            data = urlencode(data)

        auth = 'Basic {0}'.format(
            b64encode("{0}:{1}".format(self.user, self.passwd))
        )

        headers = {'Authorization': auth}

        if data is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'

        response = self._request(method, path, data, headers)
        data = json.loads(response.read())

        if 200 <= response.status < 300:
            return data
        else:
            error = data.get('error', None)
            if error is None:
                raise RobotError("Unknown error: {0}".format(data))
            else:
                err = "{0} - {1}".format(error['status'], error['message'])
                if 'missing' in error:
                    err += ", missing input: {0}".format(
                        ', '.join(error['missing'])
                    )
                if 'invalid' in error:
                    err += ", invalid input: {0}".format(
                        ', '.join(error['invalid'])
                    )
                raise RobotError(err)

    get = lambda s, p: s.request('GET', p)
    post = lambda s, p, d: s.request('POST', p, d)
    put = lambda s, p, d: s.request('PUT', p, d)
    delete = lambda s, p, d: s.request('DELETE', p, d)


class RescueSystem(object):
    def __init__(self, server):
        self.server = server
        self.conn = server.conn

        self._active = None
        self._password = None

    def _fetch_status(self):
        reply = self.conn.get('/boot/{0}/rescue'.format(self.server.ip))
        data = reply['rescue']
        self._active = data['active']
        self._password = data['password']

    @property
    def active(self):
        if self._active is not None:
            return self._active
        self._fetch_status()
        return self._active

    @property
    def password(self):
        if self._password is not None:
            return self._password
        self._fetch_status()
        return self._password

    def _rescue_action(self, method, opts=None):
        reply = self.conn.request(
            method,
            '/boot/{0}/rescue'.format(self.server.ip),
            opts
        )

        data = reply['rescue']
        self._active = data['active']
        self._password = data['password']

    def activate(self, bits=64, os='linux'):
        """
        Activate the rescue system if necessary.
        """
        if not self.active:
            opts = {'os': os, 'arch': bits}
            return self._rescue_action('post', opts)

    def deactivate(self):
        """
        Deactivate the rescue system if necessary.
        """
        if self.active:
            return self._rescue_action('delete')

    def observed_activate(self, *args, **kwargs):
        """
        Activate the rescue system and reboot into it.
        Look at Server.observed_reboot() for options.
        """
        self.activate()
        self.server.observed_reboot(*args, **kwargs)

    def observed_deactivate(self, *args, **kwargs):
        """
        Deactivate the rescue system and reboot into normal system.
        Look at Server.observed_reboot() for options.
        """
        self.deactivate()
        self.server.observed_reboot(*args, **kwargs)


class Server(object):
    def __init__(self, conn, result):
        self.conn = conn
        data = result['server']

        self.ip = data['server_ip']
        self.name = data['server_name']
        self.product = data['product']
        self.datacenter = data['dc']
        self.traffic = data['traffic']
        self.flatrate = data['flatrate']
        self.status = data['status']
        self.throttled = data['throttled']
        self.cancelled = data['cancelled']
        self.paid_until = datetime.strptime(data['paid_until'], '%Y-%m-%d')

        self.rescue = RescueSystem(self)

    def check_ssh(self, port=22, timeout=5):
        """
        Check if the current server has an open SSH port. Return True if port
        is reachable, otherwise false. Time out after 'timeout' seconds.
        """
        success = True
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(5)

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.ip, port))
            s.close()
        except socket.error:
            success = False

        socket.setdefaulttimeout(old_timeout)
        return success

    def observed_reboot(self, patience=300, tries=None, manual=False):
        """
        Reboot and wait patience seconds until the system comes back.
        If not, retry with the next step in tries and wait another patience
        seconds. Repeat until there are no more tries left.

        If manual is true, do a manual reboot in case the server doesn't come
        up again. Raises a ManualReboot exception if that is the case.

        Return True on success and False if the system didn't come up.
        """
        is_down = False

        if tries is None:
            tries = ['soft', 'hard']

        for mode in tries:
            self.reboot(mode)

            now = time.time()
            while True:
                if time.time() > now + patience:
                    break

                is_up = self.check_ssh()
                time.sleep(1)

                if is_up and is_down:
                    return
                elif not is_down:
                    is_down = not is_up
        if manual:
            self.reboot('manual')
            raise ManualReboot("Issued a manual reboot because the server"
                               " did not come back to life.")
        else:
            raise ConnectError("Server keeps playing dead after reboot :-(")

    def reboot(self, mode='soft'):
        """
        Reboot the server, modes are "soft" for reboot by triggering Ctrl-Alt-
        Del, "hard" for triggering a hardware reset and "manual" for requesting
        a poor devil from the data center to go to your server and press the
        power button.
        """
        modes = {
            'manual': 'man',
            'hard': 'hw',
            'soft': 'sw',
        }

        modekey = modes.get(mode, modes['soft'])
        return self.conn.post('/reset/{0}'.format(self.ip), {'type': modekey})

    def __repr__(self):
        return "<{0} ({1})>".format(self.ip, self.product)


class ServerManager(object):
    def __init__(self, conn):
        self.conn = conn

    def get(self, ip):
        """
        Get server by providing its main IP address.
        """
        return Server(self.conn, self.conn.get('/server/{0}'.format(ip)))

    def __iter__(self):
        return iter([Server(self.conn, s) for s in self.conn.get('/server')])


class Robot(object):
    def __init__(self, user, passwd):
        self.conn = RobotConnection(user, passwd)
        self.servers = ServerManager(self.conn)
