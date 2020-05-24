import nixops.util


class ConnectionFailed(Exception):
    pass


class CommandFailed(nixops.util.CommandFailed):
    pass
