# -*- coding: utf-8 -*-

# AWS Elastic File System mount targets.

import uuid
import boto3
import botocore
import nixops.util
import nixops.ec2_utils
import nixops.resources
import nixops.resources.ec2_common
import nixops.resources.efs_common
import time

class ElasticFileSystemMountTargetDefinition(nixops.resources.ResourceDefinition):
    """Definition of an AWS Elastic File System mount target."""

    @classmethod
    def get_type(cls):
        return "elastic-file-system-mount-target"

    @classmethod
    def get_resource_type(cls):
        return "elasticFileSystemMountTargets"

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region)

class ElasticFileSystemMountTargetState(nixops.resources.ResourceState, nixops.resources.efs_common.EFSCommonState):
    """State of an AWS Elastic File System mount target."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("ec2.accessKeyId", None)
    region = nixops.util.attr_property("ec2.region", None)
    fs_id = nixops.util.attr_property("ec2.fsId", None)
    fsmt_id = nixops.util.attr_property("ec2.fsmtId", None)
    private_ipv4 = nixops.util.attr_property("privateIpv4", None)

    @classmethod
    def get_type(cls):
        return "elastic-file-system-mount-target"

    def _reset_state(self):
        with self.depl._state.db:
            self.state = self.MISSING
            self.access_key_id = None
            self.region = None
            self.fs_id = None
            self.fsmt_id = None
            self.private_ipv4 = None

    def _exists(self):
        return self.state != self.MISSING

    def show_type(self):
        s = super(ElasticFileSystemMountTargetState, self).show_type()
        if self._exists(): s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return self.fsmt_id

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.ec2_security_group.EC2SecurityGroupState) or
                isinstance(r, nixops.resources.elastic_file_system.ElasticFileSystemState)}

    def create(self, defn, check, allow_reboot, allow_recreate):

        access_key_id = defn.config["accessKeyId"] or nixops.ec2_utils.get_access_key_id()
        region = defn.config["region"]
        client = self._get_client(access_key_id, region)

        if self.state == self.MISSING:

            self.log("creating Elastic File System mount target...")

            # Resolve the file system ID if it refers to a file system resource.
            fs_id = defn.config["fileSystem"]
            if fs_id.startswith("res-"):
                file_system = self.depl.get_typed_resource(fs_id[4:], "elastic-file-system")
                if not file_system.fs_id:
                    raise Exception("cannot create mount target for not-yet created Elastic File System ‘{0}’".format(file_system.name))
                fs_id = file_system.fs_id

            # Create the mount target. There's no client token, but
            # the request is idempotent for any file system ID +
            # subnet ID pair. A repeated call can give either a
            # MountTargetConflict error or a LifeCycleState=creating
            # response.
            args = {}
            if defn.config["ipAddress"]:
                args["IpAddress"] = defn.config["ipAddress"]

            subnetId = defn.config["subnet"]
            securityGroups = self.security_groups_to_ids(region, access_key_id, subnetId, defn.config["securityGroups"] )
            res = client.create_mount_target(FileSystemId=fs_id, SubnetId=subnetId, SecurityGroups=securityGroups, **args)

            with self.depl._state.db:
                self.state = self.STARTING
                self.fsmt_id = res["MountTargetId"]
                self.fs_id = fs_id
                self.region = defn.config["region"]
                self.access_key_id = access_key_id
                self.private_ipv4 = res["IpAddress"]

        if self.state == self.STARTING:

            self.log_start("waiting for Elastic File System mount target...")

            while True:
                mts = client.describe_mount_targets(MountTargetId=self.fsmt_id)["MountTargets"]
                assert(len(mts) <= 1)

                if len(mts) == 1:
                    mt = mts[0]
                    if mt["LifeCycleState"] == "available":
                        self.state = self.UP
                        break
                    if mt["LifeCycleState"] != "creating":
                        raise Exception("Elastic File System mount target ‘{0}’ is in unexpected state ‘{1}’".format(mt["LifeCycleState"]))

                self.log_continue(".")
                time.sleep(1)

            self.log_end(" done")

    def prefix_definition(self, attr):
        return {('resources', 'elasticFileSystemMountTargets'): attr}

    def get_physical_spec(self):
        return {
            ('ipAddress'): self.private_ipv4,
        }

    def destroy(self, wipe=False):
        if self.fsmt_id:

            self.log_start("deleting Elastic File System mount target...")

            client = self._get_client()

            try:
                client.delete_mount_target(MountTargetId=self.fsmt_id)
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] == 'MountTargetNotFound':
                    pass

            while True:
                try:
                    mts = client.describe_mount_targets(MountTargetId=self.fsmt_id)["MountTargets"]
                    assert(len(mts) <= 1)
                    if mts[0]["LifeCycleState"] == "deleted":
                        break
                    self.log_continue(".")
                    time.sleep(1)
                except botocore.exceptions.ClientError as e:
                    if e.response['Error']['Code'] == 'MountTargetNotFound':
                        break
                    time.sleep(1)

            self._reset_state()

            self.log_end(" done")

        return True

    def security_groups_to_ids(self, region, access_key_id, subnetId, groups):
        conn = nixops.ec2_utils.connect(region, access_key_id)
        conn_vpc = nixops.ec2_utils.connect_vpc(region, access_key_id)

        sg_names = filter(lambda g: not g.startswith('sg-'), groups)
        if sg_names != [ ] and subnetId != "":
            vpc_id = conn_vpc.get_all_subnets([subnetId])[0].vpc_id
            groups = map(lambda g: nixops.ec2_utils.name_to_security_group(conn, g, vpc_id), groups)

        return groups
