import unittest

from textwrap import dedent

from nixops.util import device_name_to_boto_expected


class TestDeviceNameToBotoExpected(unittest.TestCase):
    def test_device_name_to_boto_expected(self):
        self.assertEqual(
            device_name_to_boto_expected("/dev/sdf"), "/dev/sdf",
        )
        self.assertEqual(device_name_to_boto_expected("/dev/sdg"), "/dev/sdg")
        self.assertEqual(device_name_to_boto_expected("/dev/xvdf"), "/dev/sdf")
        self.assertEqual(device_name_to_boto_expected("/dev/xvdg"), "/dev/sdg")
        self.assertEqual(device_name_to_boto_expected("/dev/nvme1n1"), "/dev/sdf")
        self.assertEqual(device_name_to_boto_expected("/dev/nvme2n1"), "/dev/sdg")
        # TODO
        # self.assertEqual(
        #     device_name_to_boto_expected('/dev/nvme26n1'),
        #     '/dev/sdg'
        # )
        self.assertEqual(device_name_to_boto_expected("/dev/nvme2n1p1"), "/dev/sdg1")
        self.assertEqual(device_name_to_boto_expected("/dev/nvme2n1p6"), "/dev/sdg6")
        # TODO
        # self.assertEqual(
        #     device_name_to_boto_expected('/dev/nvme26n1p6'),
        #     '/dev/sdg6'
        # )
