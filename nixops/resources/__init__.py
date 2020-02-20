# -*- coding: utf-8 -*-

import re
import nixops.util

from nixops.state import StateDict
from nixops.diff import Diff, Handler


class ResourceDefinition(object):
    """Base class for NixOps resource definitions."""

    @classmethod
    def get_type(cls):
        """A resource type identifier that must match the corresponding ResourceState class"""
        raise NotImplementedError("get_type")

    @classmethod
    def get_resource_type(cls):
        """A resource type identifier corresponding to the resources.<type> attribute in the Nix expression"""
        return cls.get_type()

    def __init__(self, xml, config={}):
        self.config = config
        self.name = xml.get("name")
        assert self.name
        if not re.match("^[a-zA-Z0-9_\-][a-zA-Z0-9_\-\.]*$", self.name):
            raise Exception("invalid resource name ‘{0}’".format(self.name))

    def show_type(self):
        """A short description of the type of resource this is"""
        return self.get_type()


class ResourceState(object):
    """Base class for NixOps resource state objects."""

    @classmethod
    def get_type(cls):
        """A resource type identifier that must match the corresponding ResourceDefinition classs"""
        raise NotImplementedError("get_type")

    # Valid values for self.state.  Not all of these make sense for
    # all resource types.
    UNKNOWN = 0  # state unknown
    MISSING = 1  # instance destroyed or not yet created
    STARTING = 2  # boot initiated
    UP = 3  # machine is reachable
    STOPPING = 4  # shutdown initiated
    STOPPED = 5  # machine is down
    UNREACHABLE = 6  # machine should be up, but is unreachable
    RESCUE = 7  # rescue system is active for the machine

    state = nixops.util.attr_property("state", UNKNOWN, int)
    index = nixops.util.attr_property("index", None, int)
    obsolete = nixops.util.attr_property("obsolete", False, bool)

    # Time (in Unix epoch) the resource was created.
    creation_time = nixops.util.attr_property("creationTime", None, int)

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
            for n, v in list(attrs.items()):
                if v == None:
                    c.execute(
                        "delete from ResourceAttrs where machine = ? and name = ?",
                        (self.id, n),
                    )
                else:
                    c.execute(
                        "insert or replace into ResourceAttrs(machine, name, value) values (?, ?, ?)",
                        (self.id, n, v),
                    )

    def _set_attr(self, name, value):
        """Update one machine attribute in the state file."""
        self._set_attrs({name: value})

    def _del_attr(self, name):
        """Delete a machine attribute from the state file."""
        with self.depl._db:
            self.depl._db.execute(
                "delete from ResourceAttrs where machine = ? and name = ?",
                (self.id, name),
            )

    def _get_attr(self, name, default=nixops.util.undefined):
        """Get a machine attribute from the state file."""
        with self.depl._db:
            c = self.depl._db.cursor()
            c.execute(
                "select value from ResourceAttrs where machine = ? and name = ?",
                (self.id, name),
            )
            row = c.fetchone()
            if row != None:
                return row[0]
            return nixops.util.undefined

    def export(self):
        """Export the resource to move between databases"""
        with self.depl._db:
            c = self.depl._db.cursor()
            c.execute(
                "select name, value from ResourceAttrs where machine = ?", (self.id,)
            )
            rows = c.fetchall()
            res = {row[0]: row[1] for row in rows}
            res["type"] = self.get_type()
            return res

    def import_(self, attrs):
        """Import the resource from another database"""
        with self.depl._db:
            for k, v in list(attrs.items()):
                if k == "type":
                    continue
                self._set_attr(k, v)

    # XXX: Deprecated, use self.logger.* instead!
    log = lambda s, m: s.logger.log(m)
    log_start = lambda s, m: s.logger.log_start(m)
    log_continue = lambda s, m: s.logger.log_continue(m)
    log_end = lambda s, m: s.logger.log_end(m)
    warn = lambda s, m: s.logger.warn(m)
    success = lambda s, m: s.logger.success(m)

    def show_type(self):
        """A short description of the type of resource this is"""
        return self.get_type()

    def show_state(self):
        """A description of the resource's current state"""
        state = self.state
        if state == self.UNKNOWN:
            return "Unknown"
        elif state == self.MISSING:
            return "Missing"
        elif state == self.STARTING:
            return "Starting"
        elif state == self.UP:
            return "Up"
        elif state == self.STOPPING:
            return "Stopping"
        elif state == self.STOPPED:
            return "Stopped"
        elif state == self.UNREACHABLE:
            return "Unreachable"
        elif state == self.RESCUE:
            return "Rescue"
        else:
            raise Exception("machine is in unknown state")

    def prefix_definiton(self, attr):
        """Prefix the resource set with a py2nixable attrpath"""
        raise Exception("not implemented")

    def get_physical_spec(self):
        """py2nixable physical specification of the resource to be fed back into the network"""
        return {}

    def get_physical_backup_spec(self, backupid):
        """py2nixable physical specification of the specified backup"""
        return []

    @property
    def resource_id(self):
        """A unique ID to display for this resource"""
        return None

    @property
    def public_ipv4(self):
        return None

    def create_after(self, resources, defn):
        """Return a set of resources that should be created before this one."""
        return {}

    def destroy_before(self, resources):
        """Return a set of resources that should be destroyed after this one."""
        return self.create_after(resources, None)

    def create(self, defn, check, allow_reboot, allow_recreate):
        """Create or update the resource defined by ‘defn’."""
        raise NotImplementedError("create")

    def check(self):
        """
        Reconcile the state file with the real world infrastructure state.
        This should not do any provisionning but just sync the state.
        """
        self._check()

    def _check(self):
        return True

    def after_activation(self, defn):
        """Actions to be performed after the network is activated"""
        return

    def destroy(self, wipe=False):
        """Destroy this resource, if possible."""
        self.logger.warn("don't know how to destroy resource ‘{0}’".format(self.name))
        return False

    def delete_resources(self):
        """delete this resource state, if possible."""
        if not self.depl.logger.confirm(
            "are you sure you want to clear the state of {}? "
            "this will only remove the resource from the local "
            "NixOPS state and the resource may still exist outside "
            "of the NixOPS database.".format(self.name)
        ):
            return False

        self.logger.warn(
            "removing resource {} from the local NixOPS database ...".format(self.name)
        )
        return True

    def next_charge_time(self):
        """Return the time (in Unix epoch) when this resource will next incur
        a financial charge (or None if unknown)."""
        return None


class DiffEngineResourceState(ResourceState):
    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._state = StateDict(depl, id)

    def create(self, defn, check, allow_reboot, allow_recreate):
        # if --check is true check against the api and update the state
        # before firing up the diff engine in order to get the needed
        # handlers calls
        if check:
            self._check()
        diff_engine = self.setup_diff_engine(config=defn.config)

        for handler in diff_engine.plan():
            handler.handle(allow_recreate)

    def plan(self, defn):
        if hasattr(self, "_state"):
            diff_engine = self.setup_diff_engine(defn.config)
            diff_engine.plan(show=True)
        else:
            self.warn(
                "resource type {} doesn't implement a plan operation".format(
                    self.get_type()
                )
            )

    def setup_diff_engine(self, config):
        diff_engine = Diff(
            depl=self.depl,
            logger=self.logger,
            config=config,
            state=self._state,
            res_type=self.get_type(),
        )
        diff_engine.set_reserved_keys(self._reserved_keys)
        diff_engine.set_handlers(self.get_handlers())
        return diff_engine

    def get_handlers(self):
        return [
            getattr(self, h) for h in dir(self) if isinstance(getattr(self, h), Handler)
        ]

    def get_defn(self):
        if self.name in self.depl.definitions:
            return self.depl.definitions[self.name].config
        else:
            return {}
