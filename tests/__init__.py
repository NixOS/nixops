import os
import threading
from os import path
import nixops.statefile

_multiprocess_shared_ = True

db_file = '%s/test.nixops' % (path.dirname(__file__))

def setup():
    nixops.statefile.StateFile(db_file).close()

def destroy(sf, uuid):
    depl = sf.open_deployment(uuid)
    depl.auto_response = "y"
    try:
        depl.clean_backups(keep=0)
    except Exception:
        pass
    try:
        depl.destroy_resources()
    except Exception:
        pass

def teardown():
    try:
        sf = nixops.statefile.StateFile(db_file)
        uuids = sf.query_deployments()
        threads = []
        for uuid in uuids:
            threads.append(threading.Thread(target=destroy, args=(sf, uuid)))
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sf.close()
        os.remove(db_file)
