# -*- coding: utf-8 -*-

from contextlib import contextmanager
import os
import sys
import threading
from distutils.dir_util import mkpath

import nixops.state

@contextmanager
def using_state_file(state_file_path):
    create_file_parent_dirs_if_not_exists(state_file_path)

    if os.path.exists(state_file_path):
        destroy_deployments_and_remove_state_file(state_file_path)

    state = nixops.state.open(state_file_path)

    try:
        yield state
    finally:
        state.close()
        destroy_deployments_and_remove_state_file(state_file_path)


def create_file_parent_dirs_if_not_exists(file_path):
    mkpath(os.path.dirname(file_path))

def destroy_deployments(state, uuid):
    deployment = state.open_deployment(uuid)
    deployment.logger.set_autoresponse("y")
    try:
        deployment.clean_backups(keep=False, keep_days=False)
    except Exception:
        pass
    try:
        deployment.destroy_resources()
    except Exception:
        pass
    deployment.delete()
    deployment.logger.log("deployment ‘{0}’ destroyed".format(uuid))


def destroy_deployments_and_remove_state_file(state_file_path):
    state = nixops.state.open(state_file_path)
    uuids = state.query_deployments()
    threads = []
    for uuid in uuids:
        threads.append(
            threading.Thread(target=destroy_deployments, args=(state, uuid))
        )
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    uuids_left = state.query_deployments()
    state.close()
    if not uuids_left:
        os.remove(state_file_path)
    else:
        sys.stderr.write(
            "warning: not all deployments have been destroyed; some resources may still exist!\n"
        )

