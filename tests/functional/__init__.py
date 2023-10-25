from nixops.statefile import StateFile
from tests import db_file


class DatabaseUsingTest(object):
    _multiprocess_can_split_ = True

    def setup_method(self):
        self.sf = StateFile(db_file, writable=True)

    def teardown_method(self):
        self.sf.close()
