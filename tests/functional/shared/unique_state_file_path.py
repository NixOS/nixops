from nixops.util import root_dir

def unique_state_file_path(array_of_keys_file_name_depends_on, extension):
    unique_file_name = '_'.join(array_of_keys_file_name_depends_on)

    return '{}/tests/state_files/{}.{}'.format(
        root_dir, unique_file_name, extension
    )
