import os
import json
import itertools

from typing import Any, Callable, Optional, List, Dict, Union, AnyStr
import nixops.util
from nixops.logger import MachineLogger
from nixops.state import StateDict

class Diff(object):
    """
    Diff engine main class which implements methods for doing diffs between
    the state/config and generating a plan: sequence of handlers to be executed.
    """

    SET = 0
    UPDATE = 1
    UNSET = 2

    def __init__(self,
                 # FIXME: type should be 'nixops.deployment.Deployment'
                 # however we have to upgrade to python3 in order
                 # to solve the import cycle by forward declaration
                 depl,
                 logger,  # type: MachineLogger
                 config,  # type: Dict[str, Any]
                 state,  # type: StateDict
                 res_type,  # type: str
                 ):
        # type: (...) -> None
        self._definition = config
        self._state = state
        self._depl = depl
        self._type = res_type
        self.logger = logger
        self._diff = {}  # type: Dict[str, int]
        self._reserved = ['index', 'state', '_type', 'deployment', '_name',
                          'name', 'creationTime']

    def set_reserved_keys(self, keys):
        # type: (List[str]) -> None
        """
        Reserved keys are nix options or internal state keys that we don't
        want them to trigger the diff engine so we simply ignore the diff
        of the reserved keys.
        """
        self._reserved.extend(keys)

    def get_keys(self):
        # type: () -> List[str]
        diff = [k for k in self._diff.keys() if k not in self._reserved]
        return diff

    def plan(self,show=False):
        # type: (bool) -> List[Handler]
        """
        This will go through the attributes of the resource and evaluate
        the diff between definition and state then return a sorted list
        of the handlers to be called to realize the diff.
        """
        keys = self._state.keys() + self._definition.keys()
        for k in keys:
            self.eval_resource_attr_diff(k)
        for k in self.get_keys():
            definition = self.get_resource_definition(k)
            if show:
                if self._diff[k] == self.SET:
                    self.logger.log("will set attribute {0} to {1}".format(k, definition))
                elif self._diff[k] == self.UPDATE:
                    self.logger.log("{0} will be updated from {1} to {2}".format(k, self._state[k],
                                                                             definition))
                else:
                    self.logger.log("will unset attribute {0} with previous value {1} "
                                    .format(k, self._state[k]))
        return self.get_handlers_sequence()

    def set_handlers(self, handlers):
        # type: (List[Handler]) -> None
        self.handlers = handlers

    def topological_sort(self, handlers):
        # type: (List[Handler]) -> List[Handler]
        """
        Implements a topological sort of a direct acyclic graph of
        handlers using the depth first search algorithm.
        The output is a sorted sequence of handlers based on their
        dependencies.
        """
        # TODO implement cycle detection 
        parent = {}  # type: Dict[Handler, Optional[Handler]]
        sequence = []  # type: List[Handler]

        def visit(handler):
            # type: (Handler) -> None
            for v in handler.get_deps():
                if v not in parent:
                    parent[v] = handler
                    visit(v)
            sequence.append(handler)

        for h in handlers:
            if h not in parent:
                parent[h] = None
                visit(h)

        return [h for h in sequence if h in handlers]

    def get_handlers_sequence(self, combinations=1):
        # type: (int) -> List[Handler]
        if len(self.get_keys()) == 0:
            return []
        for h_tuple in itertools.combinations(self.handlers, combinations):
            keys = []
            for item in h_tuple:
                keys.extend(item.get_keys())
            if combinations == len(self.handlers):
                keys_not_found = set(self.get_keys()) - set(keys)
                if len(keys_not_found) > 0:
                    raise Exception("Couldn't find any combination of handlers"
                                    " that realize the change of {0} for resource type {1}".format(str(keys_not_found), self._type))
            if set(self.get_keys()) <= set(keys):
                handlers_seq = self.topological_sort(list(h_tuple))
                return handlers_seq
        return self.get_handlers_sequence(combinations+1)

    def eval_resource_attr_diff(self, key):
        # type: (str) -> None
        s = self._state.get(key, None)
        d = self.get_resource_definition(key)
        if s == None and d != None:
            self._diff[key] = self.SET
        elif s!=None and d == None:
            self._diff[key] = self.UNSET
        elif s!=None and d!=None:
            if s != d:
                self._diff[key] = self.UPDATE

    def get_resource_definition(self, key):
        # type: (str) -> Any
        def retrieve_def(d):
            # type: (Any) -> Any
            if isinstance(d, str) and d.startswith("res-"):
                name = d[4:].split(".")[0]
                res_type = d.split(".")[1]
                k = d.split(".")[2] if len(d.split(".")) > 2 else key
                res = self._depl.get_typed_resource(name, res_type)
                if res.state != res.UP: return "computed"
                try:
                    d = getattr(res, k)
                except AttributeError:
                    d = res._state[k]
            return d

        d = self._definition.get(key, None)
        if isinstance(d, list):
            options = []
            for option in d:
                item = retrieve_def(option)
                options.append(item)
            return options
        else:
            d = retrieve_def(d)
            return d


class Handler(object):
    def __init__(self, keys, after=None, handle=None):
        # type: (List[str], Optional[List], Optional[Callable]) -> None
        if after is None:
            after = []
        if handle is None:
            self.handle = self._default_handle
        else:
            self.handle = handle
        self._keys = keys
        self._dependencies = after

    def _default_handle(self):
        """
        Method that should be implemented to handle the changes
        of keys returned by get_keys()
        This should be done currently by monkey-patching this method
        by passing a resource state method that realizes the change.
        """
        raise NotImplementedError

    def get_deps(self):
        # type: () -> List[Handler]
        return self._dependencies

    def get_keys(self,*keys):
        # type: (*AnyStr) -> List[str]
        return self._keys
