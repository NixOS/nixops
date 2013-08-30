# -*- coding: utf-8 -*-

import re
import nixops.util


class ResourceDefinition(object):
    """Base class for NixOps resource definitions."""

    @classmethod
    def get_type(cls):
        assert False

    def __init__(self, xml):
        self.name = xml.get("name")
        assert self.name
        if not re.match("^[a-zA-Z0-9_\-][a-zA-Z0-9_\-\.]*$", self.name):
            raise Exception("invalid resource name ‘{0}’".format(self.name))

    def show_type(self):
        return self.get_type()


class ResourceState(object):
    """Base class for NixOps resource state objects."""

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
    RESCUE=7 # rescue system is active for the machine

    state = nixops.util.attr_property("state", UNKNOWN, int)
    index = nixops.util.attr_property("index", None, int)
    obsolete = nixops.util.attr_property("obsolete", False, bool)

    def __init__(self, depl, name, id):
        self.depl = depl
        self.name = name
        self.id = id
        self.logger = depl.logger.get_logger_for(name)
        self.logger.register_index(self.index)

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

    def _get_attr(self, name, default=nixops.util.undefined):
        """Get a machine attribute from the state file."""
        with self.depl._db:
            c = self.depl._db.cursor()
            c.execute("select value from ResourceAttrs where machine = ? and name = ?", (self.id, name))
            row = c.fetchone()
            if row != None: return row[0]
            return nixops.util.undefined

    def export(self):
        with self.depl._db:
            c = self.depl._db.cursor()
            c.execute("select name, value from ResourceAttrs where machine = ?", (self.id,))
            rows = c.fetchall()
            res = {row[0]: row[1] for row in rows}
            res['type'] = self.get_type()
            return res

    def import_(self, attrs):
        with self.depl._db:
            for k, v in attrs.iteritems():
                if k == 'type': continue
                self._set_attr(k, v)

    # XXX: Deprecated, use self.logger.* instead!
    log = lambda s, m: s.logger.log(m)
    log_start = lambda s, m: s.logger.log_start(m)
    log_continue = lambda s, m: s.logger.log_continue(m)
    log_end = lambda s, m: s.logger.log_end(m)
    warn = lambda s, m: s.logger.warn(m)
    success = lambda s, m: s.logger.success(m)

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
        elif state == self.RESCUE: return "In rescue system"
        else: raise Exception("machine is in unknown state")

    def prefix_definiton(self, attr):
        raise Exception("not implemented")

    def get_physical_spec(self):
        return {}

    def get_physical_backup_spec(self, backupid):
        return []

    @property
    def resource_id(self):
        return None

    def create_after(self, resources):
        """Return a set of resources that should be created before this one."""
        return {}

    def create(self, defn, check, allow_reboot, allow_recreate):
        """Create or update the resource defined by ‘defn’."""
        assert False

    def destroy(self, wipe=False):
        """Destroy this resource, if possible."""
        self.logger.warn(
            "don't know how to destroy resource ‘{0}’".format(self.name)
        )
        return False
