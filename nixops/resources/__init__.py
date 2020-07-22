# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import nixops.util
from threading import Event
from typing import List, Optional, Dict, Any, Type, TypeVar, Union, TYPE_CHECKING
from nixops.monkey import Protocol, runtime_checkable
from nixops.state import StateDict, RecordId
from nixops.diff import Diff, Handler
from nixops.util import ImmutableMapping, ImmutableValidatedObject
from nixops.logger import MachineLogger
from typing_extensions import Literal

if TYPE_CHECKING:
    import nixops.deployment


class ResourceEval(ImmutableMapping[Any, Any]):
    pass


class ResourceOptions(ImmutableValidatedObject):
    pass


class ResourceDefinition:
    """Base class for NixOps resource definitions."""

    resource_eval: ResourceEval
    config: ResourceOptions

    @classmethod
    def get_type(cls) -> str:
        """A resource type identifier that must match the corresponding ResourceState class"""
        raise NotImplementedError("get_type")

    @classmethod
    def get_resource_type(cls):
        """A resource type identifier corresponding to the resources.<type> attribute in the Nix expression"""
        return cls.get_type()

    def __init__(self, name: str, config: ResourceEval):
        config_type = self.__annotations__.get("config", ResourceOptions)

        if isinstance(config_type, str):
            if config_type == "ResourceOptions":
                raise TypeError(
                    f'{self.__class__} is missing a "config" attribute, for example: `config: nixops.resources.ResourceOptions`, see https://nixops.readthedocs.io/en/latest/plugins/authoring.html'
                )
            else:
                raise TypeError(
                    f"{self.__class__}.config's type annotation is not allowed to be a string, see: https://nixops.readthedocs.io/en/latest/plugins/authoring.html"
                )

        if not issubclass(config_type, ResourceOptions):
            raise TypeError(
                '"config" type annotation must be a ResourceOptions subclass'
            )

        self.resource_eval = config
        self.config = config_type(**config)
        self.name = name

        if not re.match("^[a-zA-Z0-9_\-][a-zA-Z0-9_\-\.]*$", self.name):  # noqa: W605
            raise Exception("invalid resource name ‘{0}’".format(self.name))

    def show_type(self) -> str:
        """A short description of the type of resource this is"""
        return self.get_type()


ResourceDefinitionType = TypeVar("ResourceDefinitionType", bound="ResourceDefinition")


@runtime_checkable
class ResourceState(Protocol[ResourceDefinitionType]):
    """Base class for NixOps resource state objects."""

    definition_type: Type[ResourceDefinitionType]

    name: str

    @classmethod
    def get_type(cls) -> str:
        """A resource type identifier that must match the corresponding ResourceDefinition class"""
        raise NotImplementedError("get_type")

    # Valid values for self.state.  Not all of these make sense for
    # all resource types.
    UNKNOWN: Literal[0] = 0  # state unknown
    MISSING: Literal[1] = 1  # instance destroyed or not yet created
    STARTING: Literal[2] = 2  # boot initiated
    UP: Literal[3] = 3  # machine is reachable
    STOPPING: Literal[4] = 4  # shutdown initiated
    STOPPED: Literal[5] = 5  # machine is down
    UNREACHABLE: Literal[6] = 6  # machine should be up, but is unreachable
    RESCUE: Literal[7] = 7  # rescue system is active for the machine

    state: Union[
        Literal[0],
        Literal[1],
        Literal[2],
        Literal[3],
        Literal[4],
        Literal[5],
        Literal[6],
        Literal[7],
    ] = nixops.util.attr_property("state", UNKNOWN, int)
    index: Optional[int] = nixops.util.attr_property("index", None, int)
    obsolete: bool = nixops.util.attr_property("obsolete", False, bool)

    # Time (in Unix epoch) the resource was created.
    creation_time: Optional[int] = nixops.util.attr_property("creationTime", None, int)

    _created_event: Optional[Event] = None
    _destroyed_event: Optional[Event] = None
    _errored: Optional[bool] = None

    # While this looks like a rookie mistake where the list is going  get shared
    # across all class instances it's not... It's working around a Mypy crash.
    #
    # We're overriding this value in __init__.
    # It's safe despite there being a shared list on the class level
    _wait_for: List["ResourceState"] = []

    depl: nixops.deployment.Deployment
    id: RecordId
    logger: MachineLogger

    def __init__(self, depl: nixops.deployment.Deployment, name: str, id: RecordId):
        # Override default class-level list.
        # Previously this behaviour was missing and the _wait_for list was shared across all instances
        # of ResourceState, resulting in a deadlock in resource destruction as they resource being
        # destroyed had a reference to itself in the _wait_for list.
        self._wait_for = []
        self.depl = depl
        self.name = name
        self.id = id
        self.logger = depl.logger.get_logger_for(name)
        if self.index is not None:
            self.logger.register_index(self.index)

    def _set_attrs(self, attrs: Dict[str, Any]) -> None:
        """Update machine attributes in the state file."""
        with self.depl._db:
            c = self.depl._db.cursor()
            for n, v in attrs.items():
                if v is None:
                    c.execute(
                        "delete from ResourceAttrs where machine = ? and name = ?",
                        (self.id, n),
                    )
                else:
                    c.execute(
                        "insert or replace into ResourceAttrs(machine, name, value) values (?, ?, ?)",
                        (self.id, n, v),
                    )

    def _set_attr(self, name: str, value: Any) -> None:
        """Update one machine attribute in the state file."""
        self._set_attrs({name: value})

    def _del_attr(self, name: str) -> None:
        """Delete a machine attribute from the state file."""
        with self.depl._db:
            self.depl._db.execute(
                "delete from ResourceAttrs where machine = ? and name = ?",
                (self.id, name),
            )

    def _get_attr(self, name: str, default=nixops.util.undefined) -> Any:
        """Get a machine attribute from the state file."""
        with self.depl._db:
            c = self.depl._db.cursor()
            c.execute(
                "select value from ResourceAttrs where machine = ? and name = ?",
                (self.id, name),
            )
            row = c.fetchone()
            if row is not None:
                return row[0]
            return nixops.util.undefined

    def export(self) -> Dict[str, Dict[str, str]]:
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
            for k, v in attrs.items():
                if k == "type":
                    continue
                self._set_attr(k, v)

    # XXX: Deprecated, use self.logger.* instead!
    def log(self, *args, **kwargs):
        return self.logger.log(*args, **kwargs)

    def log_end(self, *args, **kwargs):
        return self.logger.log_end(*args, **kwargs)

    def log_start(self, *args, **kwargs):
        return self.logger.log_start(*args, **kwargs)

    def log_continue(self, *args, **kwargs):
        return self.logger.log_continue(*args, **kwargs)

    def warn(self, *args, **kwargs):
        return self.logger.warn(*args, **kwargs)

    def success(self, *args, **kwargs):
        return self.logger.success(*args, **kwargs)

    # XXX: End deprecated methods

    def show_type(self) -> str:
        """A short description of the type of resource this is"""
        return self.get_type()

    def show_state(self) -> str:
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

    def prefix_definition(self, attr):
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
    def public_ipv4(self) -> Optional[str]:
        return None

    def create_after(self, resources, defn):
        """Return a set of resources that should be created before this one."""
        return {}

    def destroy_before(self, resources):
        """Return a set of resources that should be destroyed after this one."""
        return self.create_after(resources, None)

    def create(
        self,
        defn: ResourceDefinitionType,
        check: bool,
        allow_reboot: bool,
        allow_recreate: bool,
    ):
        """Create or update the resource defined by ‘defn’."""
        raise NotImplementedError("create")

    def check(
        self,
    ):  # TODO this return type is inconsistent with child class MachineState
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
            "NixOps state and the resource may still exist outside "
            "of the NixOps database.".format(self.name)
        ):
            return False

        self.logger.warn(
            "removing resource {} from the local NixOps database ...".format(self.name)
        )
        return True

    def next_charge_time(self):
        """Return the time (in Unix epoch) when this resource will next incur
        a financial charge (or None if unknown)."""
        return None


@runtime_checkable
class DiffEngineResourceState(
    ResourceState[ResourceDefinitionType], Protocol[ResourceDefinitionType]
):
    _reserved_keys: List[str] = []
    _state: StateDict

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._state = StateDict(depl, id)

    def create(self, defn, check, allow_reboot, allow_recreate):
        # if --check is true check against the api and update the state
        # before firing up the diff engine in order to get the needed
        # handlers calls
        if check:
            self._check()
        diff_engine = self.setup_diff_engine(defn.config)

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
            config=dict(config),
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

    def get_defn(self) -> ResourceDefinitionType:
        return self.depl.get_typed_definition(
            self.name, self.get_type(), self.definition_type
        )


GenericResourceState = ResourceState[ResourceDefinition]
