import os
from os import path
import nixops.state
from tests import db_file
from tests import json_file

class DatabaseUsingTest(object):
    _multiprocess_can_split_ = True

    def setup(self):
        self.sf = nixops.state.open(db_file)

    def teardown(self):
        self.sf.close()


class JSONUsingTest(object):
    _multiprocess_can_split_ = True

    def setup(self):
        self.sf = nixops.state.open(json_file)

    def teardown(self):
        self.sf.close()
