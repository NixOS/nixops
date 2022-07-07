from pytest import raises
from tests.functional.single_machine_test import SingleMachineTest


class TestDeletingDeletes(SingleMachineTest):
    def run_check(self):
        uuid = self.depl.uuid
        self.depl.delete()
        with raises(Exception):
            self.sf.open_deployment(uuid)
