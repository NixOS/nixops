import json
import collections

import nixops.util


class StateDict(collections.MutableMapping):
    """
       An implementation of a MutableMapping container providing
       a python dict like behavior for the NixOps state file.
    """

    # TODO implement __repr__ for convenience e.g debuging the structure
    def __init__(self, depl, id):
        super(StateDict, self).__init__()
        self._db = depl._db
        self.id = id

    def __setitem__(self, key, value):
        with self._db:
            c = self._db.cursor()
            if value == None:
                c.execute(
                    "delete from ResourceAttrs where machine = ? and name = ?",
                    (self.id, key),
                )
            else:
                v = value
                if isinstance(value, list):
                    v = json.dumps(value)
                c.execute(
                    "insert or replace into ResourceAttrs(machine, name, value) values (?, ?, ?)",
                    (self.id, key, v),
                )

    def __getitem__(self, key):
        with self._db:
            c = self._db.cursor()
            c.execute(
                "select value from ResourceAttrs where machine = ? and name = ?",
                (self.id, key),
            )
            row = c.fetchone()
            if row != None:
                try:
                    return json.loads(row[0])
                except ValueError:
                    return row[0]
            raise KeyError("couldn't find key {} in the state file".format(key))

    def __delitem__(self, key):
        with self._db:
            c.execute(
                "delete from ResourceAttrs where machine = ? and name = ?",
                (self.id, key),
            )

    def keys(self):
        # Generally the list of keys per ResourceAttrs is relatively small
        # so this should be also relatively fast.
        _keys = []
        with self._db:
            c = self._db.cursor()
            c.execute("select name from ResourceAttrs where machine = ?", (self.id,))
            rows = c.fetchall()
            for row in rows:
                _keys.append(row[0])
            return _keys

    def __iter__(self):
        return iter(list(self.keys()))

    def __len__(self):
        return len(list(self.keys()))
