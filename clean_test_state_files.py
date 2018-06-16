#! /usr/bin/env python2
# -*- coding: utf-8 -*-

from nixops.util import root_dir
from tests.functional.shared.destroy_deployments_and_remove_state_file import destroy_deployments_and_remove_state_file
from tests.functional.shared.state_files_directory import state_files_directory
import os

for file in os.listdir(state_files_directory):
    if file.endswith(".nixops") or file.endswith(".json"):
        file_path = os.path.join(state_files_directory, file)

        print("Destroying {}".format(file_path))

        destroy_deployments_and_remove_state_file(file_path)
