import os
from os import path
import nixops.statefile
from tests import db_file


class DatabaseUsingTest(object):
    _multiprocess_can_split_ = True

    def setup(self):
        self.sf = nixops.statefile.StateFile(db_file)

    def teardown(self):
        self.sf.close()
