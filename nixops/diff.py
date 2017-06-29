import json
import itertools
import nixops.util

class Diff(object):
    """
       Primitive implementation of a diff structure for experimentation
    """

    SET = 0
    UPDATE = 1
    UNSET = 2


    def __init__(self, depl, logger, config, state, res_type):
        self._definition = config
        self._state = state
        self._depl = depl
        self._type = res_type
        self.logger = logger
        self._diff = {}
        self._reserved = ['index', 'state', '_type', 'deployment', '_name',
                          'name', 'creationTime']

    def set_reserved_keys(self, keys):
        self._reserved.extend(keys)

    def get_keys(self):
        diff = [k for k in self._diff.keys() if k not in self._reserved]
        return diff

    def plan(self):
        keys = self._state.keys() + self._definition.keys()
        for k in keys:
            self.eval_resource_attr_diff(k)
        for k in self.get_keys():
            definition = self.get_resource_definition(k)
            if self._diff[k] == self.SET:
                self.logger.log("setting attribute {0} to {1}".format(k, definition))
            elif self._diff[k] == self.UPDATE:
                self.logger.log("{0} will be updated from {1} to {2}".format(k, self._state[k],
                                                                             definition))
            else:
                self.logger.log("removing attribute {0} with previous value {1} "
                                .format(k, self._state[k]))
        return self.get_handlers_sequence()

    def set_handlers(self, handlers):
        self.handlers = handlers

    def topological_sort(self, handlers):
        """
        Implements a topological sort of a direct acyclic graph of
        handlers using the depth first search algorithm.
        The output is a sorted sequence of handlers based on their
        dependencies.
        """
        # TODO implement cycle detection 
        parent = {}
        sequence = []

        def visit(handler):
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
                                    " that realize the change of {}".format(str(keys_not_found)))
            if set(self.get_keys()) <= set(keys):
                handlers_seq = self.topological_sort(list(h_tuple))
                return handlers_seq
        return self.get_handlers_sequence(combinations+1)

    def eval_resource_attr_diff(self, key):
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
        def retrieve_def(d):
            if isinstance(d, str) and d.startswith("res-"):
                name = d[4:].split(".")[0]
                res_type = d.split(".")[1]
                k = d.split(".")[2] if len(d.split(".")) > 2 else key
                res = self._depl.get_typed_resource(name, res_type)
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
        if after is None:
            after = []
        if handle is not None:
            self.handle = handle
        self._keys = keys
        self._dependencies = after

    def handle(self):
        """
        Method that should be implemented to handle the changes
        of keys returned by get_keys()
        This should be done currently by monkey-patching this method
        by passing a resource state method that realizes the change.
        """
        raise NotImplementedError

    def get_deps(self):
        return self._dependencies

    def get_keys(self,*keys):
        return self._keys
