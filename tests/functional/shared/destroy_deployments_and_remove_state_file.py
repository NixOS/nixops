# -*- coding: utf-8 -*-

import nixops.state
import threading
import os
import sys

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
        message = "warning: not all deployments have been destroyed; some resources may still exist!\n"
        sys.stderr.write(message)

def destroy_deployments(state, uuid):
    deployment = state.open_deployment(uuid)
    deployment.logger.set_autoresponse("y")

    try:
        deployment.clean_backups(keep=False, keep_days=False)
    except Exception as e:
        deployment.logger.error("on clean backups for deployment ‘{}’: {}".format(uuid, e))

    try:
        deployment.destroy_resources()
    except Exception as e:
        deployment.logger.error("on destroy resources for deployment ‘{}’: {}".format(uuid, e))

    deployment.delete()
    deployment.logger.log("deployment ‘{}’ destroyed".format(uuid))
