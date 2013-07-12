from nose import tools

from tests.functional import single_machine_test


class TestDeletingDeletes(single_machine_test.SingleMachineTest):
    def run_check(self):
        uuid = self.depl.uuid
        self.depl.delete()
        tools.assert_raises(Exception, self.sf.open_deployment, (uuid,))
