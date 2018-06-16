from tests.functional.shared.state_files_directory import state_files_directory

def unique_state_file_path(array_of_keys_file_name_depends_on, extension):
    unique_file_name = '_'.join(array_of_keys_file_name_depends_on)

    return '{}/{}.{}'.format(state_files_directory, unique_file_name, extension)
