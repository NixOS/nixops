import os
from os import path

from charon import deployment

_multiprocess_shared_ = True

db_file = '%s/test.charon' % (path.dirname(__file__))

def setup():
    deployment.open_database(db_file).close()

def teardown():
    os.remove(db_file)
