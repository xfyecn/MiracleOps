import paramiko
from paramiko.ssh_exception import AuthenticationException, SSHException
from tornado.websocket import WebSocketClosedError
from .ioloop import IOLoop
from .models import *
from asset.models import *

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO


class Bridge(object):
    def __init__(self, websocket):
        self._websocket = websocket
        self._shell = None
        self._id = 0
        self.ssh = paramiko.SSHClient()
        # record every session id
        self._t_id = ''

    @property
    def id(self):
        return self._id

    @property
    def websocket(self):
        return self._websocket

    @property
    def shell(self):
        return self._shell

    def privaterKey(self, _PRIVATE_KEY, _PRIVATE_KEY_PWD):
        try:
            pkey = paramiko.RSAKey.from_private_key(StringIO(_PRIVATE_KEY), _PRIVATE_KEY_PWD)
        except paramiko.SSHException:
            pkey = paramiko.DSSKey.from_private_key(StringIO(_PRIVATE_KEY), _PRIVATE_KEY_PWD)
        return pkey

    def isPassword(self, data):
        return data.get("ispwd", True)

    def open(self, data={}):
        self.ssh.set_missing_host_key_policy(
            paramiko.AutoAddPolicy())
        try:
            self.ssh.connect(hostname=data["host"], port=int(data["port"]), username=data["username"])
        except AuthenticationException:
            raise Exception("auth failed user:%s ,passwd:%s" %
                            (data["username"], data["secret"]))
        except SSHException:
            raise Exception("could not connect to host:%s:%s" %
                            (data["hostname"], data["port"]))
        # create one row to record terminal session
        _server = Server.objects.get(pk=data['id'])
        Terminal.objects.create(server=_server, status=1, t_id=data['t_id'])
        self._t_id = data['t_id']
        self.establish()

    def establish(self, term="xterm"):
        self._shell = self.ssh.invoke_shell(term)
        self._shell.setblocking(0)

        self._id = self._shell.fileno()
        IOLoop.instance().register(self)
        IOLoop.instance().add_future(self.trans_back())

    def trans_forward(self, data=""):
        if self._shell:
            self._shell.send(data)

    def trans_back(self):
        yield self.id
        connected = True
        while connected:
            result = yield
            if self._websocket:
                try:
                    self._websocket.write_message(result)
                except WebSocketClosedError:
                    connected = False
                if result.strip() == 'logout':
                    connected = False
        self.destroy()

    def destroy(self):
        self._websocket.close()
        self.ssh.close()
        Terminal.objects.filter(t_id=self._t_id).delete()