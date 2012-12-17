import os
from os import path
import sqlite3

from charon import deployment

from tests import db_file


class DatabaseUsingTest(object):
    _multiprocess_can_split_ = True

    def setup(self):
        self.db = sqlite3.connect(db_file, timeout=60, check_same_thread=False, factory=deployment.Connection)
        self.db.db_file = db_file

    def teardown(self):
        self.db.close()
