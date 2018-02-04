# -*- coding: utf-8 -*-

# AWS Elastic File Systems.

import uuid
import boto3
import botocore
import nixops.util
import nixops.ec2_utils
import nixops.resources
import nixops.resources.ec2_common
import nixops.resources.efs_common
import time

class ElasticFileSystemDefinition(nixops.resources.ResourceDefinition):
    """Definition of an AWS Elastic File System."""

    @classmethod
    def get_type(cls):
        return "elastic-file-system"

    @classmethod
    def get_resource_type(cls):
        return "elasticFileSystems"

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region)

class ElasticFileSystemState(nixops.resources.ResourceState, \
                             nixops.resources.ec2_common.EC2CommonState, \
                             nixops.resources.efs_common.EFSCommonState):
    """State of an AWS Elastic File System."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("ec2.accessKeyId", None)
    region = nixops.util.attr_property("ec2.region", None)
    fs_id = nixops.util.attr_property("ec2.fsId", None)
    creation_token = nixops.util.attr_property("ec2.creationToken", None)

    @classmethod
    def get_type(cls):
        return "elastic-file-system"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)

    def _exists(self):
        return self.state != self.MISSING

    def show_type(self):
        s = super(ElasticFileSystemState, self).show_type()
        if self._exists(): s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return self.fs_id

    def create(self, defn, check, allow_reboot, allow_recreate):

        access_key_id = defn.config["accessKeyId"] or nixops.ec2_utils.get_access_key_id()

        client = self._get_client(access_key_id, defn.config["region"])

        if self.state == self.MISSING:

            self.log_start("creating Elastic File System...")

            if not self.creation_token:
                self.creation_token = str(uuid.uuid4())
                self.state = self.STARTING

            # FIXME: implement security groups.

            try:
                client.create_file_system(CreationToken=self.creation_token)
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] == 'FileSystemAlreadyExists':
                    pass

            while True:
                fss = client.describe_file_systems(CreationToken=self.creation_token)["FileSystems"]
                assert(len(fss) <= 1)

                if len(fss) == 1:
                    fs = fss[0]
                    if fs["LifeCycleState"] == "available":
                        with self.depl._state.db:
                            self.state = self.UP
                            self.fs_id = fs["FileSystemId"]
                            self.region = defn.config["region"]
                            self.access_key_id = access_key_id
                            self.creation_token = None
                        break
                    if fs["LifeCycleState"] != "creating":
                        raise Exception("Elastic File System ‘{0}’ is in unexpected state ‘{1}’".format(fs["LifeCycleState"]))

                self.log_continue(".")
                time.sleep(1)

            self.log_end(" done")

        def tag_updater(tags):
            # FIXME: handle removing tags.
            client.create_tags(FileSystemId=self.fs_id, Tags=[{"Key": k, "Value": tags[k]} for k in tags])

        self.update_tags_using(tag_updater, user_tags=defn.config["tags"], check=check)

    # Override the regular default tag because EFS doesn't allow '['
    # and ']' in tag values.
    def get_default_name_tag(self):
        return "{0} - {1}".format(self.depl.description, self.name)

    def destroy(self, wipe=False):
        assert not self.creation_token # FIXME: handle this case

        if self.fs_id:

            if not self.depl.logger.confirm("are you sure you want to destroy Elastic File System ‘{0}’?".format(self.name)):
                return False

            self.log_start("deleting Elastic File System...")

            client = self._get_client()

            mts = client.describe_mount_targets(FileSystemId=self.fs_id)["MountTargets"]
            if len(mts) > 0:
                raise Exception("cannot delete Elastic File System ‘{0}’ because it still has mount targets".format(self.name))

            try:
                client.delete_file_system(FileSystemId=self.fs_id)
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] == 'FileSystemNotFound':
                    pass

            while True:
                try:
                    fss = client.describe_file_systems(FileSystemId=self.fs_id)["FileSystems"]
                    assert(len(fss) == 1)
                    if fss[0]["LifeCycleState"] == "deleted":
                        break
                    self.log_continue(".")
                    time.sleep(1)
                except botocore.exceptions.ClientError as e:
                    if e.response['Error']['Code'] == 'FileSystemNotFound':
                        break
                    time.sleep(1)

            with self.depl._state.db:
                self.state = self.MISSING
                self.fs_id = None
                self.region = None
                self.access_key_id = None

            self.log_end(" done")

        return True
