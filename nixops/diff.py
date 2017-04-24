import nixops.util

class Diff(object):
    """
       Primitive implementation of a diff structure for experimentation
    """

    CREATE = 0
    UPDATE = 1
    DESTROY = 2
    _reserved = [ 'index', 'state', '_type', 'deployment', '_name',
            'name', 'creationTime' ]

    def __init__(self, depl, logger, config, state, res_type, enable_handler=False):
        self._definition = config
        self._state = state
        self._depl = depl
        self._type = res_type
        self.logger = logger
        self.enable_handler = enable_handler
        self._diff = {}

    def set_reserved_keys(self, keys):
        self._reserved.extend(keys)

    def plan(self):
        keys = self._state.keys() + self._definition.keys()
        for k in keys:
            self.eval_resource_attr_diff(k)
        for k in self._diff.keys() :
            if k not in self._reserved:
                if self._diff[k] == self.CREATE:
                    self.logger.log("creation: {0}:{1}".format(k, self._definition[k]))
                elif self._diff[k] == self.UPDATE:
                    self.logger.log("{0} will be updated from {1} to {2}".format(k, self._state[k],
                        self._definition[k]))
                    if self.enable_handler:
                        self.handle_change(self._depl,k)
                else:
                    self.logger.log("{0} with state {1} will be destroyed".format(k, self._state[k]))

    def eval_resource_attr_diff(self, key):
        s = self._state.get(key, None)
        d = self._definition.get(key, None)
        if s==None and d != None:
            self._diff[key] = self.CREATE
        elif s!=None and d == None:
            self._diff[key] = self.DESTROY
        else:
            if s != d:
                self._diff[key] = self.UPDATE

    def handle_change(self, depl, key):
        """
          Initial handler of a diff engine. Not used anywhere
        """
        resource = depl.get_typed_resource(self._definition['_name'], self._type)
        handler = "handle_{0}_change".format(key)
        if handler in dir(resource):
            method = getattr(resource, handler)
            method()
        else:
            self.logger.warn('no handler found for {0} change'.format(key))
