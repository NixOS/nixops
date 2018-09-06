import unittest

from textwrap import dedent

from nixops.util import device_name_to_sd

class TestDeviceNameToSd(unittest.TestCase):
    def test_device_name_to_sd(self):
        self.assertEqual(
            device_name_to_sd('/dev/sdf'),
            '/dev/sdf',
        )
        self.assertEqual(
            device_name_to_sd('/dev/sdg'),
            '/dev/sdg'
        )
        self.assertEqual(
            device_name_to_sd('/dev/xvdf'),
            '/dev/sdf'
        )
        self.assertEqual(
            device_name_to_sd('/dev/xvdg'),
            '/dev/sdg'
        )
        self.assertEqual(
            device_name_to_sd('/dev/nvme1n1'),
            '/dev/sdf'
        )
        self.assertEqual(
            device_name_to_sd('/dev/nvme2n1'),
            '/dev/sdg'
        )
        # TODO
        # self.assertEqual(
        #     device_name_to_sd('/dev/nvme26n1'),
        #     '/dev/sdg'
        # )
        self.assertEqual(
            device_name_to_sd('/dev/nvme2n1p1'),
            '/dev/sdg1'
        )
        self.assertEqual(
            device_name_to_sd('/dev/nvme2n1p6'),
            '/dev/sdg6'
        )
        # TODO
        # self.assertEqual(
        #     device_name_to_sd('/dev/nvme26n1p6'),
        #     '/dev/sdg6'
        # )
