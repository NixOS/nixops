from nose import tools
from nixops import deployment

from tests.functional import single_machine_test

class TestDeletingDeletes(single_machine_test.SingleMachineTest):
    def run_check(self):
        uuid = self.depl.uuid
        self.depl.delete()
        tools.assert_raises(Exception, deployment.open_deployment, (self.depl._db, uuid))
