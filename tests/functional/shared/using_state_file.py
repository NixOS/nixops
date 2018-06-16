from contextlib import contextmanager
import os
import sys
from distutils.dir_util import mkpath

import nixops.state
from tests.functional.shared.destroy_deployments_and_remove_state_file import destroy_deployments_and_remove_state_file

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
