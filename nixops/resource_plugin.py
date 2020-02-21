#
import pluggy


class NixOpsPluginSpec(object):
    """A hook specification namespace.
    """

    @hookspec  # type: ignore
    def load(self):
        """My special little hook that you can customize.
        """
