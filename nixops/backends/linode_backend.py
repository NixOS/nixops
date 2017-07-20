# -*- coding: utf-8 -*-

import os

from time import sleep

import linode
from nixops.nix_expr import Function, RawValue
from nixops.backends import MachineDefinition, MachineState
from nixops.util import attr_property, create_key_pair

INFECT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'nixos-infect.linode'))

class NoInstanceIdError(Exception):
    pass

class LinodeDefinition(MachineDefinition):
    @classmethod
    def get_type(cls):
        return "linode"

    def __init__(self, xml, config):
        MachineDefinition.__init__(self, xml, config)

        self.region_id = config["linode"]["region"]
        self.type_id = config["linode"]["type"]
        self.personal_api_key = config["linode"]["personalAPIKey"]

    def show_type(self):
        return "{0} {1} {2}".format(self.get_type(), self.region_id, self.type_id)

class LinodeState(MachineState):
    @staticmethod
    def get_type():
        return "linode"

    ## Data to be stored in statefile
    linode_id = attr_property("linode.linodeID", None)
    public_ipv4 = attr_property("publicIpv4", None)
    public_ipv6 = attr_property("publicIpv6", {}, 'json')
    private_key = attr_property("privateKey", None)
    public_key = attr_property("public", None)

    ## Temporarily cached values about the deployment
    _deployment_name = None
    _personal_api_key = None

    ## Temporarily cached Linode API objects
    _linode_client = None
    _linode_instance = None

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)

        self._deployment_name = depl.name or depl.uuid
        self.name = name

        try:
            depl.definitions
        except AttributeError:
            depl.evaluate()

        defn = depl.definitions[name]

        self._personal_api_key = defn.personal_api_key

        if not self.private_key:
            (self.private_key, self.public_key) = create_key_pair()

    @staticmethod
    def get_plan(client, type_id):
        for t in client.linode.get_types():
            if type_id == t.id:
                return t

        raise ValueError("Unknown type id %s" % self._type_id)

    @staticmethod
    def get_region(client, region_id):
        for r in client.get_regions():
            if region_id == r.id:
                return r

        raise ValueError("Unknown region id %s" % self._region_id)

    @staticmethod
    def get_kernel(client, kernel_label):
        for k in client.linode.get_kernels():
            if k.deprecated or not k.x64 or not k.kvm:
                pass
            elif k.label == kernel_label:
                return k

        raise ValueError("Unknown kernel id 'Direct Disk'")

    @staticmethod
    def get_kernel_direct_disk(client):
        return LinodeState.get_kernel(client, "Direct Disk")

    @staticmethod
    def get_kernel_grub(client):
        return LinodeState.get_kernel(client, "GRUB 2")

    @staticmethod
    def get_debian(client):
        for d in client.linode.get_distributions(linode.Distribution.vendor == "Debian"):
            if d.id == "linode/debian8":
                return d

        raise ValueError("Unknown distribution 'Debian 8'")

    @staticmethod
    def try_until_success(f):
        try:
            return f()
        except linode.ApiError as e:
            if e.status == 400 and e.errors[0] == "Linode busy.":
                sleep(0.1)
                return LinodeState.try_until_success(f)
            else:
                raise

    def get_personal_api_key(self):
        if not self._personal_api_key:
            self._personal_api_key = os.environ.get('LINODE_PERSONAL_API_KEY')

        if not self._personal_api_key:
            raise RuntimeError("Neither deployment.linode.personalAPIKey nor the LINODE_PERSONAL_API_KEY variable was set.")

        return self._personal_api_key


    def get_client(self):
        if not self._linode_client:
            key = self.get_personal_api_key()

            if key is None:
                raise RuntimeError("Attempted to create A Linode client, but could not find a Linode personal API key.")

            self._linode_client = linode.LinodeClient(key)

        return self._linode_client

    def get_linode_instance(self):
        if not self._linode_instance:
            if not self.linode_id:
                raise NoInstanceIdError("Attempted to get a Linode instance, but we have no linode_id stored yet. Has this machine actually been created?")

            self._linode_instance = linode.Linode(self.get_client(), self.linode_id)

        return self._linode_instance

    def get_ssh_private_key_file(self):
        return self.write_ssh_private_key(self.private_key)

    def get_ssh_name(self):
        return self.public_ipv4

    def get_ssh_flags(self, *args, **kwargs):
        super_flags = super(LinodeState, self).get_ssh_flags(*args, **kwargs)
        return super_flags + [
            '-o', 'UserKnownHostsFile=/dev/null',
            '-o', 'StrictHostKeyChecking=no',
            '-i', self.get_ssh_private_key_file()
        ]

    def get_physical_spec(self):
        return {
            'imports': [ RawValue('<nixpkgs/nixos/modules/profiles/qemu-guest.nix>') ],
            ('boot', 'loader', 'grub'): {
                'device': '/dev/sda',
                'forceInstall': True
            },
            ('fileSystems', '/'): {
                'device': '/dev/sda',
                'fsType': 'ext4'
            },
            'swapDevices': [
                { 'device': '/dev/sdb' }
            ],
            ('users', 'extraUsers', 'root', 'openssh', 'authorizedKeys', 'keys'): [self.public_key]
        }

    def start(self):
        return self.get_linode_instance().boot()

    def stop(self):
        self.log_start("Shutting down")

        instance = self.get_linode_instance()

        instance.shutdown()
        self.state = self.STOPPING

        while instance.status != "offline":
            self.log_continue(".")
            sleep(1)

        self.state = self.STOPPED
        self.ssh_master = None

        self.log_end("Shutdown complete")


    def reboot_rescue(self):
        instance = self.get_linode_instance()

        return instance.rescue([instance.disks[0].id])

    def destroy(self, wipe = False):
        try:
            return self.get_linode_instance().delete()
        except NoInstanceIdError:
            return True

    def get_label(self):
        """
        Return a valid Linode label.

        We'd like it to be descriptive, so we use the machine name.

        It must be unique. Hopefully the machine name + deployment
        name meets this criteria.

        It can't be more than 32 characters, so we truncate it.

        It must end with a latter or number, so we continue truncating
        it until that is true.
        """
        label = (self.name + "-" + self._deployment_name)[0:30]

        while not label[-1].isalnum():
            if len(label) == 0:
                raise RuntimeError("Could not create a valid label for machine with name %s and deployment id %s" % (self.name, self._deployment_name))

            label = label[0:-1]

        return label

    def create(self, defn, check, allow_reboot, allow_recreate):
        client = self.get_client()

        if self.linode_id is not None:
            instance = linode.Linode(client, self.linode_id)

            try:
                instance.status # Force a get request to check whether this instance already exists.
                return True # We don't need to do anything to create this instance.
            except linode.ApiError as e:
                if e.status == 404:
                    pass
                else:
                    raise


        plan = LinodeState.get_plan(client, defn.type_id)

        service = linode.Service(client, plan.id)

        instance = None

        try:
            self.log_start("Creating Linode instance")
            instance = client.linode.create_instance(
                service,
                LinodeState.get_region(client, defn.region_id),
                distribution = LinodeState.get_debian(client),
                label = self.get_label(),
                group = "nixops-" + self._deployment_name,
                root_ssh_key = self.public_key
            )[0]

            if not instance:
                raise RuntimeError("Failed to create Linode instance " + self.name + " " + self._deployment_name)

            self.linode_id = instance.id
            self.public_ipv4 = instance.ipv4[0]
            self.public_ipv6 = instance.ipv6

            self.log_end("")
            self.log_start("Booting instance into Debian 8 with standard Grub 2 kernel.")

            ## Changing configuration to Grub 2 lets us use the
            ## default Debian kernel instead of Linode's modified
            ## kernel (which has a weird disk setup and causes
            ## problems).

            config = instance.configs[0]
            config.kernel = LinodeState.get_kernel_grub(client)
            config.save()

            instance.boot()

            self.wait_for_ssh()

            self.log_end("")

            self.log_start("running nixos-infect")
            self.run_command('bash </dev/stdin 2>&1', stdin=open(INFECT_PATH))
            self.log_end("")
            self.stop()

            self.log_start("Booting instance into Nixos")
            ## nixos-infect installs Grub on the disk - we want to switch to using that.
            config.kernel = LinodeState.get_kernel_direct_disk(client)
            config.save()

            instance.boot()

            self.wait_for_ssh()

            self.log_end("")

        except:
            if instance:
                instance.delete()
            self.linode_id = None

            raise
