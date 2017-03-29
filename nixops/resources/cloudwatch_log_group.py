# -*- coding: utf-8 -*-

# Automatic provisioning of AWS cloudwatch log groups.

import boto
import boto.logs
import nixops.util
import nixops.resources
import nixops.ec2_utils

class CloudWatchLogGroupDefinition(nixops.resources.ResourceDefinition):
    """Definition of a cloudwatch log group."""

    @classmethod
    def get_type(cls):
        return "cloudwatch-log-group"

    @classmethod
    def get_resource_type(cls):
        return "cloudwatchLogGroups"

    def show_type(self):
        return "{0}".format(self.get_type())

class CloudWatchLogGroupState(nixops.resources.ResourceState):
    """State of the cloudwatch log group"""
    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    log_group_name = nixops.util.attr_property("cloudwatch.logGroupName", None)
    region = nixops.util.attr_property("cloudwatch.region", None)
    access_key_id = nixops.util.attr_property("cloudwatch.accessKeyId", None)
    retention_in_days = nixops.util.attr_property("cloudwatch.logGroupRetentionInDays", None, int)
    arn = nixops.util.attr_property("cloudwatch.logGroupARN", None)

    @classmethod
    def get_type(cls):
        return "cloudwatch-log-group"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._conn = None

    def show_type(self):
        s = super(CloudWatchLogGroupState, self).show_type()
        if self.region: s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return self.log_group_name

    def prefix_definition(self, attr):
        return {('resources', 'cloudwatchLogGroups'): attr}

    def get_physical_spec(self):
        return {'arn': self.arn}

    def get_definition_prefix(self):
        return "resources.cloudwatchLogGroups."

    def connect(self):
        if self._conn: return
        assert self.region
        (access_key_id, secret_access_key) = nixops.ec2_utils.fetch_aws_secret_key(self.access_key_id)
        self._conn = boto.logs.connect_to_region(
            region_name=self.region, aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)

    def _destroy(self):
        if self.state != self.UP: return
        self.connect()
        self.log("destroying cloudwatch log group ‘{0}’...".format(self.log_group_name))
        try:
         self._conn.delete_log_group(self.log_group_name)
        except  boto.logs.exceptions.ResourceNotFoundException, e:
            self.log("the log group ‘{0}’ was already deleted".format(self.log_group_name))
        with self.depl._state.db:
            self.state = self.MISSING
            self.log_group_name = None
            self.region = None
            self.retention_in_days = None
            self.arn = None

    def lookup_cloudwatch_log_group(self, log_group_name, next_token=None):
        if log_group_name:
         response = self._conn.describe_log_groups(log_group_name_prefix=log_group_name,next_token=next_token)
         if 'logGroups' in response:
          for log in response['logGroups']:
              if log_group_name == log['logGroupName']:
                  return True, log['arn']
         if 'nextToken' in response:
             self.lookup_cloudwatch_log_group(log_group_name_prefix=log_group_name,next_token=response['nextToken'])
        return False, None

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set ‘accessKeyId’, $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        if self.state == self.UP and (self.log_group_name != defn.config['name'] or self.region != defn.config['region']):
            self.log("cloudwatch log group definition changed, recreating...")
            self._destroy()
            self._conn = None

        self.region = defn.config['region']
        self.connect()
        exist, arn = self.lookup_cloudwatch_log_group(log_group_name=self.log_group_name)

        if self.arn == None or not exist:
            self.retention_in_days = None
            self.log("creating cloudwatch log group ‘{0}’...".format(defn.config['name']))
            log_group = self._conn.create_log_group(defn.config['name'])
            exist, arn = self.lookup_cloudwatch_log_group(log_group_name=defn.config['name'])

        if self.retention_in_days != defn.config['retentionInDays']:
            self.log("setting the retention in days of '{0}' to '{1}'".format(defn.config['name'], defn.config['retentionInDays']))
            self._conn.set_retention(log_group_name=defn.config['name'],retention_in_days=defn.config['retentionInDays'])

        with self.depl._state.db:
            self.state = self.UP
            self.log_group_name = defn.config['name']
            self.region = defn.config['region']
            self.arn = arn
            self.retention_in_days = defn.config['retentionInDays']

    def destroy(self, wipe=False):
        self._destroy()
        return True
