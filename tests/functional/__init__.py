import os
from os import path
import sqlite3

from charon import deployment

from tests import db_file

_multiprocess_can_split_ = True

_db = None

db = lambda: _db

def setup():
    global _db
    _db = sqlite3.connect(db_file, timeout=60, check_same_thread=False, factory=deployment.Connection)
    _db.db_file = db_file

def teardown():
    db().close()
