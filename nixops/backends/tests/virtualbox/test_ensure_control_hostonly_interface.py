# -*- coding: utf-8 -*-

from unittest import TestCase

from textwrap import dedent

# --------------------------------------------------------------------------- #
class DummyLogger(object):

    # ....................................................................... #
    def __init__(self):
        pass

    # ....................................................................... #
    def confirm(self, question):
        pass

    # ....................................................................... #
    def log(self, message):
        pass

# --------------------------------------------------------------------------- #
class DummyDeployment(object):

    # ....................................................................... #
    def __init__(self):
        self.logger = DummyLogger()


# --------------------------------------------------------------------------- #
class TestVirtualBoxBackend_ensure_control_hostonly_interface(TestCase):

    # ....................................................................... #
    def _makeOne(self):

        from nixops.backends import MachineState

        # patch MachineState because none of this functionality uses
        # MachineState
        def dummy_init(obj, depl, name, id):
            obj.depl = depl
            obj.logger = depl.logger
        MachineState.__init__ = dummy_init

        from nixops.backends.virtualbox import VirtualBoxState

        # create the VirtualBoxState instance
        self.vbox_state = VirtualBoxState(
            depl=DummyDeployment(),
            name="test_name",
            id="test_id")

        return self.vbox_state

    # ....................................................................... #
    def _callFUT(self):
        # call function under test, and we do not care about the return
        self.vbox_state.ensure_control_hostonly_interface()

    # ....................................................................... #
    def test_not_vboxnet0_missing_interface_exception(self):
        """
        Control Host-Only interface not vboxnet0, are no interfaces exception

        Testing for:
           - VirtualBoxBackendError with the correct error message
        """

        from nixops.backends.virtualbox import VirtualBoxBackendError

        test_hostonlyif_name = "vboxnet1"

        # ~~~~~~~~~~~~~~~~ #
        # create test instance
        vbox_state = self._makeOne()

        # patch in the non-vboxnet0 interface
        vbox_state.vbox_control_hostonlyif_name = test_hostonlyif_name

        # desired exception message
        desired_err_msg = "VirtualBox Host-Only Interface {0} does not exist".format(test_hostonlyif_name)

        # ~~~~~~~~~~~~~~~~ #
        # setup and patch logged_exec
        def logged_exec(command, **kwargs):

            # dummy the return of "VBoxManage list hostonlyifs" that echos
            # no interfaces
            if command == ["VBoxManage", "list", "hostonlyifs"]:
                return ""

            # dummy the return of "VBoxManage list dhcpservers" that echos
            # no dhcpservers
            if command == ["VBoxManage", "list", "dhcpservers"]:
                return ""
        vbox_state._logged_exec = logged_exec

        # ~~~~~~~~~~~~~~~~ #
        # test that an exception with correct message was raised
        self.assertRaisesRegexp(
            VirtualBoxBackendError,
            desired_err_msg,
            self._callFUT)

    # ....................................................................... #
    def test_not_vboxnet0_dhcpserver_not_configured_exception(self):
        """
        Control Host-Only interface not vboxnet0, DHCP not configured exception
        (self.vbox_control_hostonlyif_name is set to vboxne1)

        Testing for:
           - VirtualBoxBackendError with the correct error message
        """

        from nixops.backends.virtualbox import VirtualBoxBackendError

        test_hostonlyif_name = "vboxnet1"

        # ~~~~~~~~~~~~~~~~ #
        # create test instance
        vbox_state = self._makeOne()

        # patch in the non-vboxnet0 interface
        vbox_state.vbox_control_hostonlyif_name = test_hostonlyif_name

        # desired exception message
        desired_err_msg = "VirtualBox Host-Only Interface {0} does not have a DHCP server attached".format(test_hostonlyif_name)

        # ~~~~~~~~~~~~~~~~ #
        # setup and patch logged_exec
        def logged_exec(command, **kwargs):

            # dummy the return of "VBoxManage list hostonlyifs" that echos
            # only vboxnet1 host-only interface and no vboxnet0 interface
            if command == ["VBoxManage", "list", "hostonlyifs"]:
                return dedent("""\
                    Name:            vboxnet1
                    GUID:            786f6276-656e-4074-8000-0a0027000000
                    DHCP:            Disabled
                    IPAddress:       192.168.56.1
                    NetworkMask:     255.255.255.0
                    IPV6Address:
                    IPV6NetworkMaskPrefixLength: 0
                    HardwareAddress: 0a:00:27:00:00:00
                    MediumType:      Ethernet
                    Status:          Down
                    VBoxNetworkName: HostInterfaceNetworking-vboxnet1

                """)

            # dummy the return of "VBoxManage list dhcpservers" that has no
            # DHCP server for any interfaces
            if command == ["VBoxManage", "list", "dhcpservers"]:
                return ""
        vbox_state._logged_exec = logged_exec

        # ~~~~~~~~~~~~~~~~ #
        # test that an exception with correct message was raised
        self.assertRaisesRegexp(
            VirtualBoxBackendError,
            desired_err_msg,
            self._callFUT)

    # ....................................................................... #
    def test_not_vboxnet0_dhcpserver_disabled_exception(self):
        """
        Control Host-Only inteface not vboxnet0, DHCP disabled exception
        (self.vbox_control_hostonlyif_name is set to vboxne1)

        Testing for:
           - VirtualBoxBackendError with the correct error message
        """

        from nixops.backends.virtualbox import VirtualBoxBackendError

        test_hostonlyif_name = "vboxnet1"

        # ~~~~~~~~~~~~~~~~ #
        # create test instance
        vbox_state = self._makeOne()

        # patch in the non-vboxnet0 interface
        vbox_state.vbox_control_hostonlyif_name = test_hostonlyif_name

        # desired exception returns
        desired_err_msg = "VirtualBox Host-Only Interface {0} DHCP server is disabled".format(test_hostonlyif_name)

        # ~~~~~~~~~~~~~~~~ #
        # setup and patch logged_exec
        def logged_exec(command, **kwargs):

            # dummy the return of "VBoxManage list dhcpservers" that echos
            # only vboxnet1 host-only interface and no vboxnet0 interface
            if command == ["VBoxManage", "list", "hostonlyifs"]:
                return dedent("""\
                    Name:            vboxnet1
                    GUID:            786f6276-656e-4074-8000-0a0027000000
                    DHCP:            Disabled
                    IPAddress:       192.168.56.1
                    NetworkMask:     255.255.255.0
                    IPV6Address:
                    IPV6NetworkMaskPrefixLength: 0
                    HardwareAddress: 0a:00:27:00:00:00
                    MediumType:      Ethernet
                    Status:          Down
                    VBoxNetworkName: HostInterfaceNetworking-vboxnet1

                """)

            # dummy the return of "VBoxManage list dhcpservers" that echos
            # the disabled DHCP server for the vboxnet1
            if command == ["VBoxManage", "list", "dhcpservers"]:
                return dedent("""\
                    NetworkName:    HostInterfaceNetworking-vboxnet1
                    IP:             0.0.0.0
                    NetworkMask:    0.0.0.0
                    lowerIPAddress: 0.0.0.0
                    upperIPAddress: 0.0.0.0
                    Enabled:        No

                """)

        vbox_state._logged_exec = logged_exec

        # ~~~~~~~~~~~~~~~~ #
        # test that an exception with correct message was raised
        self.assertRaisesRegexp(
            VirtualBoxBackendError,
            desired_err_msg,
            self._callFUT)

    # ....................................................................... #
    def test_when_vboxnet0_is_missing_create_and_add_dhcpserver(self):
        """
        Creating a missing vboxnet0 interface and its DHCP server, test logging

        Testing for:
            - User confirmation that we want to create the interface by
              regexing the ask message
            - creation of the vboxnet0 interface
            - configuring of the vboxnet interface with proper settings
            - creation for the DHCP server for the vboxnet and configuring
              it with the proper settings

        Also testing for logging of the following:
            - Control Host-Only Interface Name
            - Control Host-Only Interface IP Address
            - Control Host-Only Interface Network Mask
            - Control Host-Only Interface DHCP Server IP Address
            - Control Host-Only Interface DHCP Server Network Mask
            - Control Host-Only Interface DHCP Server Lower IP
            - Control HostOnly Interface DHCP Server Upper IP

        """

        # setup the test values
        test_hostonlyif_name = "vboxnet0"
        test_host_ip4 = "test_host_ip4"
        test_host_ip4_netmask = "test_host_ip4_netmask"
        test_dhcpserver_ip = "test_dhcpserver_ip"
        test_dhcpserver_netmask = "test_dhcpserver_netmask"
        test_dhcpserver_lowerip = "test_dhcpserver_lowerip"
        test_dhcpserver_upperip = "test_dhcpserver_upperip"

        desired_log_message = dedent("""\
            Control Host-Only Interface Name                    : {0}
            Control Host-Only Interface IP Address              : {1}
            Control Host-Only Interface Network Mask            : {2}
            Control Host-Only Interface DHCP Server IP Address  : {3}
            Control Host-Only Interface DHCP Server Network Mask: {4}
            Control Host-Only Interface DHCP Server Lower IP    : {5}
            Control Host-Only Interface DHCP Server Upper IP    : {6}
            """).format(
                test_hostonlyif_name,
                test_host_ip4,
                test_host_ip4_netmask,
                test_dhcpserver_ip,
                test_dhcpserver_netmask,
                test_dhcpserver_lowerip,
                test_dhcpserver_upperip).rstrip()


        # ~~~~~~~~~~~~~~~~ #
        # create test instance
        vbox_state = self._makeOne()

        # patch in host ip and dhcp server ip settings
        vbox_state.vbox_control_hostonlyif_name = test_hostonlyif_name
        vbox_state.vbox_control_host_ip4 = test_host_ip4
        vbox_state.vbox_control_host_ip4_netmask = test_host_ip4_netmask
        vbox_state.vbox_control_dhcpserver_ip = test_dhcpserver_ip
        vbox_state.vbox_control_dhcpserver_netmask = test_dhcpserver_netmask
        vbox_state.vbox_control_dhcpserver_lowerip = test_dhcpserver_lowerip
        vbox_state.vbox_control_dhcpserver_upperip = test_dhcpserver_upperip

        # ~~~~~~~~~~~~~~~~ #
        # setup all the test values to False
        test_results = {
            "confirm_interface_create_ask_prompt": False,
            "confirm_create_command": False,
            "confirm_ipconfig_command": False,
            "confirm_dhcpserver_add_command": False,
            "returned_log_message": [],
        }

        # ~~~~~~~~~~~~~~~~ #
        # setup and patch logged_exec
        def logged_exec(command, **kwargs):

            # dummy the return of "VBoxManage list hostonlyifs" that echos
            # no interfaces
            if command == ["VBoxManage", "list", "hostonlyifs"]:
                return ""

            # dummy the return of "VBoxManage list dhcpsservers" that echos
            # no DHCP servers
            if command == ["VBoxManage", "list", "dhcpservers"]:
                return ""

            # record the call for creation virtualbox hostonlyif interface
            if command == ["VBoxManage", "hostonlyif", "create"]:
                test_results["confirm_create_command"] = True
                return True

            # record the call for for virtualbox hostonly ipconfig
            if command == ["VBoxManage", "hostonlyif", "ipconfig",
                           test_hostonlyif_name,
                           "--ip", test_host_ip4,
                           "--netmask", test_host_ip4_netmask]:
                test_results["confirm_ipconfig_command"] = True
                return True

            # record the call for for virtualbox dhcpserver additions
            if command == ["VBoxManage", "dhcpserver", "add",
                           "--ifname", test_hostonlyif_name,
                           "--ip", test_dhcpserver_ip,
                           "--netmask", test_dhcpserver_netmask,
                           "--lowerip", test_dhcpserver_lowerip,
                           "--upperip", test_dhcpserver_upperip,
                           "--enable"]:
                test_results["confirm_dhcpserver_add_command"] = True
                return True
        vbox_state._logged_exec = logged_exec

        # ~~~~~~~~~~~~~~~~ #
        # patch <state>.deploy.confirm method for deployment logger to
        # says 'yes' when asked to create host-only interface
        def logger_confirm_yes(question):
            msg = "To control VirtualBox VMs ‘{0}’ Host-Only interface is "\
                "needed, create one?".format(test_hostonlyif_name)
            if question == msg:
                test_results["confirm_interface_create_ask_prompt"] = True
                return True
            return False
        vbox_state.depl.logger.confirm = logger_confirm_yes


        # ~~~~~~~~~~~~~~~~ #
        # patch <state>.log method for the state to test the logging statements
        # recording all information about
        def log_return(msg):
            test_results["returned_log_message"].append(msg)
        vbox_state.log = log_return

        # ~~~~~~~~~~~~~~~~ #
        # call function under test #
        self._callFUT()

        # ~~~~~~~~~~~~~~~~ #
        # test that ask prompt, create, ipconfiog and DHCP server add commands
        # ran successfully
        self.assertTrue(test_results["confirm_interface_create_ask_prompt"])
        self.assertTrue(test_results["confirm_create_command"])
        self.assertTrue(test_results["confirm_ipconfig_command"])
        self.assertTrue(test_results["confirm_dhcpserver_add_command"])

        # ~~~~~~~~~~~~~~~~ #

        print "---"
        print '\n'.join(test_results["returned_log_message"])
        print "---"
        print desired_log_message
        print "---"

        # test logging output
        self.assertEquals(desired_log_message, '\n'.join(test_results["returned_log_message"]))


    # ....................................................................... #
    def test_enabling_dhcpserver_on_existing_vboxnet0(self):
        """
        Enable an existing DHCP server on an existing vboxnet0

        Testing for:
            - User confirmation that we want to have the DHCP server enabled
              and configured with our settings
            - enabling a DHCP server for the vboxnet and configuring
              it with the proper settings
        """

        # setup the test values
        test_hostonlyif_name = "vboxnet0"
        test_dhcpserver_ip = "test_dhcpserver_ip"
        test_dhcpserver_netmask = "test_dhcpserver_netmask"
        test_dhcpserver_lowerip = "test_dhcpserver_lowerip"
        test_dhcpserver_upperip = "test_dhcpserver_upperip"

        # ~~~~~~~~~~~~~~~~ #
        # create test instance
        vbox_state = self._makeOne()

        # patch in host ip and dhcp server ip settings
        vbox_state.vbox_control_dhcpserver_ip = test_dhcpserver_ip
        vbox_state.vbox_control_dhcpserver_netmask = test_dhcpserver_netmask
        vbox_state.vbox_control_dhcpserver_lowerip = test_dhcpserver_lowerip
        vbox_state.vbox_control_dhcpserver_upperip = test_dhcpserver_upperip

        # ~~~~~~~~~~~~~~~~ #
        # setup all the test values to False
        test_results = {
            "confirm_enable_dhcpserver_ask_prompt": False,
            "confirm_dhcpserver_add_command": False,
        }

        # ~~~~~~~~~~~~~~~~ #
        # setup and patch logged_exec
        def logged_exec(command, **kwargs):

            # dummy the return of "VBoxManage list hostonlyifs" that echos
            # a vboxnet0 interface
            if command == ["VBoxManage", "list", "hostonlyifs"]:
                return dedent("""\
                    Name:            vboxnet0
                    GUID:            786f6276-656e-4074-8000-0a0027000000
                    DHCP:            Disabled
                    IPAddress:       192.168.56.1
                    NetworkMask:     255.255.255.0
                    IPV6Address:
                    IPV6NetworkMaskPrefixLength: 0
                    HardwareAddress: 0a:00:27:00:00:00
                    MediumType:      Ethernet
                    Status:          Down
                    VBoxNetworkName: HostInterfaceNetworking-vboxnet0

                """)

            # dummy the return of "VBoxManage list dhcpsservers" that echos
            # no DHCP servers
            if command == ["VBoxManage", "list", "dhcpservers"]:
                return ""

            # record the call for for virtualbox dhcpserver additions
            if command == ["VBoxManage", "dhcpserver", "add",
                           "--ifname", test_hostonlyif_name,
                           "--ip", test_dhcpserver_ip,
                           "--netmask", test_dhcpserver_netmask,
                           "--lowerip", test_dhcpserver_lowerip,
                           "--upperip", test_dhcpserver_upperip,
                           "--enable"]:
                test_results["confirm_dhcpserver_add_command"] = True
                return True
        vbox_state._logged_exec = logged_exec

        # ~~~~~~~~~~~~~~~~ #
        # patch confirm method always says yes when asked enable and configure
        # the DHCP server
        def logger_confirm_yes(question):
            msg = "To control VirtualBox VMs ‘{0}’ Host-Only interface "\
                    "needs to have DHCP Server enabled and it settings "\
                    "configured. This may potentially override your previous "\
                    "VirtualBox setup. Continue?"\
                    .format(test_hostonlyif_name)
            if question == msg:
                test_results["confirm_enable_dhcpserver_ask_prompt"] = True
                return True
            return False
        vbox_state.depl.logger.confirm = logger_confirm_yes

        # ~~~~~~~~~~~~~~~~ #
        # call function under test #
        self._callFUT()

        # ~~~~~~~~~~~~~~~~ #
        # test that we asked for a prompts to enable and configure DHCP server
        self.assertTrue(test_results["confirm_enable_dhcpserver_ask_prompt"])
        # test that we issued DHCP server add command
        self.assertTrue(test_results["confirm_dhcpserver_add_command"])

    # ....................................................................... #
    def test_adding_dhcpserver_to_existing_vboxnet0(self):
        """
        Adding a missing DHCP server to vboxnet0

        Testing for:
            - User confirmation that we want to have the DHCP server enabled
              and configured with our settings
            - creation for the DHCP server for the vboxnet and configuring
              it with the proper settings
        """

        # setup the test values
        test_hostonlyif_name = "vboxnet0"
        test_dhcpserver_ip = "test_dhcpserver_ip"
        test_dhcpserver_netmask = "test_dhcpserver_netmask"
        test_dhcpserver_lowerip = "test_dhcpserver_lowerip"
        test_dhcpserver_upperip = "test_dhcpserver_upperip"

        # ~~~~~~~~~~~~~~~~ #
        # create test instance
        vbox_state = self._makeOne()

        # patch in host ip and dhcp server ip settings
        vbox_state.vbox_control_dhcpserver_ip = test_dhcpserver_ip
        vbox_state.vbox_control_dhcpserver_netmask = test_dhcpserver_netmask
        vbox_state.vbox_control_dhcpserver_lowerip = test_dhcpserver_lowerip
        vbox_state.vbox_control_dhcpserver_upperip = test_dhcpserver_upperip

        # ~~~~~~~~~~~~~~~~ #
        # setup all the test values to False
        test_results = {
            "confirm_enable_dhcpserver_ask_prompt": False,
            "confirm_dhcpserver_modify_command": False,
        }

        # ~~~~~~~~~~~~~~~~ #
        # setup and patch logged_exec
        def logged_exec(command, **kwargs):

            # dummy the return of "VBoxManage list hostonlyifs" that echos
            # a vboxnet0 interface
            if command == ["VBoxManage", "list", "hostonlyifs"]:
                return dedent("""\
                    Name:            vboxnet0
                    GUID:            786f6276-656e-4074-8000-0a0027000000
                    DHCP:            Disabled
                    IPAddress:       192.168.56.1
                    NetworkMask:     255.255.255.0
                    IPV6Address:
                    IPV6NetworkMaskPrefixLength: 0
                    HardwareAddress: 0a:00:27:00:00:00
                    MediumType:      Ethernet
                    Status:          Down
                    VBoxNetworkName: HostInterfaceNetworking-vboxnet0

                """)

            # dummy the return of "VBoxManage list dhcpsservers" that echos
            # no DHCP servers
            if command == ["VBoxManage", "list", "dhcpservers"]:
                return dedent("""\
                    NetworkName:    HostInterfaceNetworking-vboxnet0
                    IP:             192.168.56.100
                    NetworkMask:    255.255.255.0
                    lowerIPAddress: 192.168.56.101
                    upperIPAddress: 192.168.56.254
                    Enabled:        No

                    """)

            # record the call for for virtualbox dhcpserver additions
            if command == ["VBoxManage", "dhcpserver", "modify",
                           "--ifname", test_hostonlyif_name,
                           "--ip", test_dhcpserver_ip,
                           "--netmask", test_dhcpserver_netmask,
                           "--lowerip", test_dhcpserver_lowerip,
                           "--upperip", test_dhcpserver_upperip,
                           "--enable"]:
                test_results["confirm_dhcpserver_modify_command"] = True
                return True
        vbox_state._logged_exec = logged_exec

        # ~~~~~~~~~~~~~~~~ #
        # patch confirm always says yes
        def logger_confirm_yes(question):
            msg = "To control VirtualBox VMs ‘{0}’ Host-Only interface "\
                    "needs to have DHCP Server enabled and it settings "\
                    "configured. This may potentially override your previous "\
                    "VirtualBox setup. Continue?"\
                    .format(test_hostonlyif_name)
            if question == msg:
                test_results["confirm_enable_dhcpserver_ask_prompt"] = True
                return True
            return False
        vbox_state.depl.logger.confirm = logger_confirm_yes

        # ~~~~~~~~~~~~~~~~ #
        # call function under test #
        self._callFUT()

        # ~~~~~~~~~~~~~~~~ #
        # test that we asked for a prompts to enable and configure DHCP server
        self.assertTrue(test_results["confirm_enable_dhcpserver_ask_prompt"])
        # test that we issued DHCP server modify command
        self.assertTrue(test_results["confirm_dhcpserver_modify_command"])
