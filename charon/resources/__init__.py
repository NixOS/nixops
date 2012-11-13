import charon.util


class ResourceDefinition(object):
    """Base class for Charon resource definitions."""

    @classmethod
    def get_type(cls):
        assert False

    def __init__(self, xml):
        self.name = xml.get("name")
        assert self.name

    def show_type(self):
        return self.get_type()


class ResourceState(object):
    """Base class for Charon resource state objects."""

    @classmethod
    def get_type(cls):
        assert False

    # Valid values for self.state.  Not all of these make sense for
    # all resource types.
    UNKNOWN=0 # state unknown
    MISSING=1 # instance destroyed or not yet created
    STARTING=2 # boot initiated
    UP=3 # machine is reachable
    STOPPING=4 # shutdown initiated
    STOPPED=5 # machine is down
    UNREACHABLE=6 # machine should be up, but is unreachable

    state = charon.util.attr_property("state", UNKNOWN, int)
    index = charon.util.attr_property("index", None, int)
    obsolete = charon.util.attr_property("obsolete", False, bool)

    def __init__(self, depl, name, id):
        self.depl = depl
        self.name = name
        self.id = id
        self.set_log_prefix(0)

    def _set_attrs(self, attrs):
        """Update machine attributes in the state file."""
        with self.depl._db:
            c = self.depl._db.cursor()
            for n, v in attrs.iteritems():
                if v == None:
                    c.execute("delete from ResourceAttrs where machine = ? and name = ?", (self.id, n))
                else:
                    c.execute("insert or replace into ResourceAttrs(machine, name, value) values (?, ?, ?)",
                              (self.id, n, v))

    def _set_attr(self, name, value):
        """Update one machine attribute in the state file."""
        self._set_attrs({name: value})

    def _del_attr(self, name):
        """Delete a machine attribute from the state file."""
        with self.depl._db:
            self.depl._db.execute("delete from ResourceAttrs where machine = ? and name = ?", (self.id, name))

    def _get_attr(self, name, default=charon.util.undefined):
        """Get a machine attribute from the state file."""
        with self.depl._db:
            c = self.depl._db.cursor()
            c.execute("select value from ResourceAttrs where machine = ? and name = ?", (self.id, name))
            row = c.fetchone()
            if row != None: return row[0]
            return charon.util.undefined

    def set_log_prefix(self, length):
        self._log_prefix = "{0}{1}> ".format(self.name, '.' * (length - len(self.name)))
        if self.depl._log_file.isatty() and self.index != None:
            self._log_prefix = "\033[1;{0}m{1}\033[0m".format(31 + self.index % 7, self._log_prefix)

    def log(self, msg):
        self.depl.log(self._log_prefix + msg)

    def log_start(self, msg):
        self.depl.log_start(self._log_prefix, msg)

    def log_continue(self, msg):
        self.depl.log_start(self._log_prefix, msg)

    def log_end(self, msg):
        self.depl.log_end(self._log_prefix, msg)

    def warn(self, msg):
        self.log(charon.util.ansi_warn("warning: " + msg, outfile=self.depl._log_file))

    def show_type(self):
        return self.get_type()

    def show_state(self):
        state = self.state
        if state == self.UNKNOWN: return "Unknown"
        elif state == self.MISSING: return "Missing"
        elif state == self.STARTING: return "Starting"
        elif state == self.UP: return "Up"
        elif state == self.STOPPING: return "Stopping"
        elif state == self.STOPPED: return "Stopped"
        elif state == self.UNREACHABLE: return "Unreachable"
        else: raise Exception("machine is in unknown state")

    @property
    def resource_id(self):
        return None

    def create(self, defn, check, allow_reboot):
        """Create or update the resource defined by ‘defn’."""
        assert False

    def destroy(self):
        """Destroy this resource, if possible."""
        self.warn("don't know how to destroy resource ‘{0}’".format(self.name))
        return False
