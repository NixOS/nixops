from tests.functional.shared.using_state_file import using_state_file
from tests.functional.shared.unique_state_file_path import unique_state_file_path

def using_unique_state_file(
        array_of_keys_file_name_depends_on,
        extension):
    return using_state_file(
                unique_state_file_path(
                    array_of_keys_file_name_depends_on,
                    extension
                )
            )
