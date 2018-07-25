import boto3
import botocore.exceptions
import botocore.errorfactory

import nixops.util
import nixops.resources
import nixops.ec2_utils
from nixops.resources.ec2_common import EC2CommonState


class EC2RDSDbSubnetGroupDefinition(nixops.resources.ResourceDefinition):

    @classmethod
    def get_type(cls):
        return "ec2-rds-dbsubnet-group"

    @classmethod
    def get_resource_type(cls):
        return "rdsDbSubnetGroups"

    def __init__(self, xml):
        nixops.resources.ResourceDefinition.__init__(self, xml)
        self.region = xml.find("attrs/attr[@name='region']/string").get("value")
        self.access_key_id = xml.find("attrs/attr[@name='accessKeyId']/string").get("value")

        self.group_name = xml.find("attrs/attr[@name='groupName']/string").get("value")
        self.description = xml.find("attrs/attr[@name='description']/string").get("value")
        self.subnet_ids = []
        for s in xml.findall("attrs/attr[@name='subnetIds']/list"):
            for s_str in s.findall("string"):
                s_name = s_str.get("value")
                self.subnet_ids.append(s_name)

    def show_type(self):
        return "{0}".format(self.get_type())


class EC2RDSDbSubnetGroupState(nixops.resources.ResourceState):

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)

    region = nixops.util.attr_property("ec2.region", None)
    access_key_id = nixops.util.attr_property("ec2.accessKeyId", None)

    group_name = nixops.util.attr_property("rdsDbSubnetGroups.groupName", None)
    description = nixops.util.attr_property("rdsDbSubnetGroups.description", None)
    subnet_ids = nixops.util.attr_property("rdsDbSubnetGroups.subnetIds", [], 'json')

    @classmethod
    def get_type(cls):
        return "ec2-rds-dbsubnet-group"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._conn = None

    def show_type(self):
        s = super(EC2RDSDbSubnetGroupState, self).show_type()
        return "{0} [{1}]".format(s, self.region)

    @property
    def resource_id(self):
        return self.group_name

    def _connect(self):
        if self._conn:
            return
        (access_key_id, secret_access_key) = nixops.ec2_utils.fetch_aws_secret_key(self.access_key_id)
        self._conn = boto3.session.Session(region_name=self.region,
                                           aws_access_key_id=access_key_id,
                                           aws_secret_access_key=secret_access_key)

    def _try_fetch_dbsubnet_group(self, group_name):
        dbsubnet_group = None
        rdsclient = self._conn.client('rds')
        try:
            response = rdsclient.describe_db_subnet_groups(
                DBSubnetGroupName=group_name
            )
            dbsubnet_group = response['DBSubnetGroups'][0]
        except rdsclient.exceptions.DBSubnetGroupNotFoundFault as e:
            dbsubnet_group = None
        return dbsubnet_group

    def _compare_instance_group_name(self, group_name):
        return unicode(self.group_name).lower() == unicode(group_name).lower()

    def create(self, defn, check, allow_reboot, allow_recreate):
        with self.depl._db:
            self.access_key_id = defn.access_key_id or nixops.ec2_utils.get_access_key_id()
            if not self.access_key_id:
                raise Exception("please set ‘accessKeyId’, $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")
            self.region = defn.region

        self._connect()
        rdsclient = self._conn.client('rds')
        dbsubnet_group = self._try_fetch_dbsubnet_group(defn.group_name)
        subnet_ids = []
        for s in defn.subnet_ids:
            if s.startswith("res-"):
                res = self.depl.get_typed_resource(s[4:].split(".")[0], "vpc-subnet")
                subnet_ids.append(res._state['subnetId'])
            else:
                subnet_ids.append(s)

        if self.state == self.UP:
            if dbsubnet_group and not self._compare_instance_group_name(defn.group_name):
                raise Exception("group_name changed but RDS dbsubnet_group with group_name=%s already exists" % defn.group_name)
            dbsubnet_group = self._try_fetch_dbsubnet_group(self.group_name)

        with self.depl._db:
            if check or self.state == self.MISSING or self.state == self.UNKNOWN:
                if dbsubnet_group and (self.state == self.MISSING or self.state == self.UNKNOWN):
                    self.logger.log("RDS dbsubnet_group '%s' is MISSING but already exists, synchronizing state" % defn.group_name)
                    self.state = self.UP

                if not dbsubnet_group and self.state == self.UP:
                    self.logger.log("RDS dbsubnet_group '%s' state is UP but does not exist!" % self.group_name)
                    if not allow_recreate:
                        raise Exception("RDS dbsubnet_group is UP but does not exist, set --allow-recreate to recreate")
                    self.state = self.MISSING

                if not dbsubnet_group and (self.state == self.MISSING or self.state == self.UNKNOWN):
                    self.logger.log("creating RDS dbsubnet_group %s" % defn.group_name)

                    rdsclient.create_db_subnet_group(
                        DBSubnetGroupName=defn.group_name,
                        DBSubnetGroupDescription=defn.description,
                        SubnetIds=subnet_ids)
                    self.state = self.STARTING

            self.group_name = defn.group_name
            self.description = defn.description
            self.subnet_ids = subnet_ids
            self.state = self.UP

    def destroy(self, wipe=False):
        if self.state == self.UP or self.state == self.STARTING:
            if not self.depl.logger.confirm("are you sure you want to destroy RDS dbsubnet_group '%s'?" % self.group_name):
                return False
            self._connect()
            rdsclient = self._conn.client('rds')

            dbsubnet_group = None
            if self.group_name:
                dbsubnet_group = self._try_fetch_dbsubnet_group(self.group_name)

            if dbsubnet_group:
                self.logger.log("destroying RDS dbsubnet_group '%s'" % self.group_name)
                try:
                    rdsclient.delete_db_subnet_group(DBSubnetGroupName=self.group_name)
                except botocore.exceptions.ClientError as error:
                    if error.response['Error']['Code'] == 'DBSubnetGroupNotFound':
                        self.logger.log("RDS dbsubnet_group '%s' does not exist, skipping." % self.group_name)
                    else:
                        raise error

            with self.depl._db:
                self.state = self.MISSING
                self.region = None
                self.group_name = None
                self.description = None
                self.subnet_ids = None
        return True
