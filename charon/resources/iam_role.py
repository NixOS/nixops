# -*- coding: utf-8 -*-

# Automatic provisioning of AWS IAM roles.

import time
import boto
import boto.iam
import charon.util
import charon.resources
import charon.ec2_utils
from xml.etree import ElementTree
from pprint import pprint

class IAMRoleDefinition(charon.resources.ResourceDefinition):
    """Definition of an IAM Role."""

    @classmethod
    def get_type(cls):
        return "iam-role"

    def __init__(self, xml):
        charon.resources.ResourceDefinition.__init__(self, xml)
        self.role_name = xml.find("attrs/attr[@name='name']/string").get("value")
        self.access_key_id = xml.find("attrs/attr[@name='accessKeyId']/string").get("value")
        self.policy = xml.find("attrs/attr[@name='policy']/string").get("value")

    def show_type(self):
        return "{0}".format(self.get_type())


class IAMRoleState(charon.resources.ResourceState):
    """State of an IAM Role."""

    state = charon.util.attr_property("state", charon.resources.ResourceState.MISSING, int)
    role_name = charon.util.attr_property("ec2.roleName", None)
    access_key_id = charon.util.attr_property("ec2.accessKeyId", None)
    policy = charon.util.attr_property("ec2.policy", None)

    @classmethod
    def get_type(cls):
        return "iam-role"


    def __init__(self, depl, name, id):
        charon.resources.ResourceState.__init__(self, depl, name, id)
        self._conn = None


    def show_type(self):
        s = super(IAMRoleState, self).show_type()
        return s


    @property
    def resource_id(self):
        return self.role_name


    def connect(self):
        if self._conn: return
        (access_key_id, secret_access_key) = charon.ec2_utils.fetch_aws_secret_key(self.access_key_id)
        self._conn = boto.connect_iam(
            aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)


    def _destroy(self):
        if self.state != self.UP: return
        self.connect()

        try:
            ip = self._conn.get_instance_profile(self.role_name)
            try:
                self._conn.remove_role_from_instance_profile(self.role_name, self.role_name)
            except:
                self.log("Could not remove role from instance profile. Perhaps already gone.")

            try:
                self._conn.get_role_policy(self.role_name, self.role_name)
                self.log("Removing role policy")
                self._conn.delete_role_policy(self.role_name, self.role_name)
            except:
                self.log("Could not find role policy")

            try:
                self._conn.get_role(self.role_name)
                self.log("Removing role")
                self._conn.delete_role(self.role_name)
            except:
                self.log("Could not find role")

            self.log("Removing instance profile")
            self._conn.delete_instance_profile(self.role_name)

        except:
            self.log("Could not find instance profile")


        with self.depl._db:
            self.state = self.MISSING
            self.role_name = None
            self.access_key_id = None
            self.policy = None


    def create_after(self, resources):
        # IAM roles can refer to S3 buckets.
        return {r for r in resources if
                isinstance(r, charon.resources.s3_bucket.S3BucketState)}


    def create(self, defn, check, allow_reboot):

        self.access_key_id = defn.access_key_id or charon.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set ‘accessKeyId’, $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        if self.state == self.UP and (self.role_name != defn.role_name):
            self.log("role definition changed, recreating...")
            self._destroy()

        if check or self.state != self.UP:

            self.connect()

            try:
                r = self._conn.get_instance_profile(defn.role_name)
            except:
                r = None

            if not r or self.state != self.UP:
                if r:
                    self.log("deleting role ‘{0}’ (and ...".format(defn.role_name))
                    self._destroy()
                self.log("creating IAM role ‘{0}’...".format(defn.role_name))
                profile = self._conn.create_instance_profile(defn.role_name, '/')
                role = self._conn.create_role(defn.role_name)
                self._conn.add_role_to_instance_profile(defn.role_name, defn.role_name)
                self._conn.put_role_policy(defn.role_name, defn.role_name, defn.policy)

            with self.depl._db:
                self.state = self.UP
                self.role_name = defn.role_name
                self.policy = defn.policy


    def destroy(self):
        self._destroy()
        return True
