# -*- coding: utf-8 -*-

# Automatic provisioning of EC2 key pairs.

from __future__ import absolute_import

import boto3

import nixops.ec2_utils
import nixops.resources
import nixops.util


class EC2KeyPairDefinition(nixops.resources.ResourceDefinition):
    """Definition of an EC2 key pair."""

    @classmethod
    def get_type(cls):
        # type: () -> str
        return "ec2-keypair"

    @classmethod
    def get_resource_type(cls):
        # type: () -> str
        return "ec2KeyPairs"

    def __init__(self, xml):
        # type: (...) -> None
        super(EC2KeyPairDefinition, self).__init__(xml)

        self.keypair_name = xml.find("attrs/attr[@name='name']/string").get("value")
        self.region = xml.find("attrs/attr[@name='region']/string").get("value")
        self.profile = xml.find("attrs/attr[@name='profile']/string").get("value")
        self.access_key_id = xml.find("attrs/attr[@name='accessKeyId']/string").get("value")

    def show_type(self):
        # type: () -> str
        return "{0} [{1}]".format(self.get_type(), self.region)


class EC2KeyPairState(nixops.resources.ResourceState):
    """State of an EC2 key pair."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    keypair_name = nixops.util.attr_property("ec2.keyPairName", None)
    public_key = nixops.util.attr_property("publicKey", None)
    private_key = nixops.util.attr_property("privateKey", None)
    profile = nixops.util.attr_property("ec2.profile", None)
    access_key_id = nixops.util.attr_property("ec2.accessKeyId", None)
    region = nixops.util.attr_property("ec2.region", None)

    @classmethod
    def get_type(cls):
        return "ec2-keypair"

    def __init__(self, depl, name, id):
        super(EC2KeyPairState, self).__init__(depl, name, id)
        self._session = None  # type: boto3.session.Session

    def show_type(self):
        s = super(EC2KeyPairState, self).show_type()
        if self.region:
            s = "{0} [{1}]".format(s, self.region)

        return s

    @property
    def resource_id(self):
        return self.keypair_name

    @staticmethod
    def get_definition_prefix():
        return "resources.ec2KeyPairs."

    def session(self):
        # type: () -> boto3.Session

        if not self._session:
            self._session = nixops.ec2_utils.session(**{
                "region_name": self.region,
                "profile_name": self.profile,
                "aws_access_key_id": self.access_key_id
            })

        return self._session

    def create(self, defn, check, allow_reboot, allow_recreate):
        # type: (EC2KeyPairDefinition, bool, bool, bool) -> None

        self.profile = defn.profile
        self.access_key_id = defn.access_key_id or nixops.ec2_utils.get_access_key_id()

        # Generate the key pair locally.
        if not self.public_key:
            private, public = nixops.util.create_key_pair(type="rsa")  # EC2 only supports RSA keys.
            with self.depl._db:
                self.public_key = public
                self.private_key = private

        # Upload the public key to EC2.
        if check or self.state != self.UP:
            self.region = defn.region

            ec2 = self.session().client('ec2')
            keys = ec2.describe_key_pairs(Filters=[{'Name': 'key-name', 'Values': [defn.keypair_name]}])

            # Don't re-upload the key if it exists and we're just checking.
            if not keys['KeyPairs'] or self.state != self.UP:
                if keys['KeyPairs']:
                    ec2.delete_key_pair(KeyName=defn.keypair_name)
                self.log("uploading EC2 key pair ‘{0}’...".format(defn.keypair_name))
                ec2.import_key_pair(KeyName=defn.keypair_name, PublicKeyMaterial=self.public_key.encode())

            with self.depl._db:
                self.state = self.UP
                self.keypair_name = defn.keypair_name

    def destroy(self, wipe=False):
        for m in self.depl.active_resources.values():
            if isinstance(m, nixops.backends.ec2.EC2State) and m.key_pair == self.keypair_name:
                raise Exception("keypair ‘{0}’ is still in use by ‘{1}’ ({2})".format(self.keypair_name, m.name, m.vm_id))

        if not self.depl.logger.confirm("are you sure you want to destroy keypair ‘{0}’?".format(self.keypair_name)):
            return False

        if self.state == self.UP:
            self.log("deleting EC2 key pair ‘{0}’...".format(self.keypair_name))
            ec2 = self.session().client('ec2')
            ec2.delete_key_pair(KeyName=self.keypair_name)

        return True

    def check(self):
        ec2 = self.session().client('ec2')

        keys = ec2.describe_key_pairs(Filters=[{'Name': 'key-name', 'Values': [self.keypair_name]}])
        if not keys['KeyPairs']:
            self.state = self.MISSING
