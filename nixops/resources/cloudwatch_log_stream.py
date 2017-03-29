# -*- coding: utf-8 -*-

# Automatic provisioning of AWS cloudwatch log streams.

import boto
import boto.logs
import nixops.util
import nixops.resources
import nixops.ec2_utils

class CloudWatchLogStreamDefinition(nixops.resources.ResourceDefinition):
    """Definition of a cloudwatch log stream."""

    @classmethod
    def get_type(cls):
        return "cloudwatch-log-stream"

    @classmethod
    def get_resource_type(cls):
        return "cloudwatchLogStreams"

    def show_type(self):
        return "{0}".format(self.get_type())

class CloudWatchLogStreamState(nixops.resources.ResourceState):
    """State of the cloudwatch log group"""
    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    log_stream_name = nixops.util.attr_property("cloudwatch.logStreamName", None)
    log_group_name = nixops.util.attr_property("cloudwatch.logGroupName", None)
    region = nixops.util.attr_property("cloudwatch.region", None)
    access_key_id = nixops.util.attr_property("cloudwatch.accessKeyId", None)
    arn = nixops.util.attr_property("cloudwatch.logStreamARN", None)

    @classmethod
    def get_type(cls):
        return "cloudwatch-log-stream"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._conn = None

    def show_type(self):
        s = super(CloudWatchLogStreamState, self).show_type()
        if self.region: s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return self.log_stream_name

    def prefix_definition(self, attr):
        return {('resources', 'cloudwatchLogStreams'): attr}

    def get_physical_spec(self):
        return {'arn': self.arn}

    def get_definition_prefix(self):
        return "resources.cloudwatchLogStreams."

    def connect(self):
        if self._conn: return
        assert self.region
        (access_key_id, secret_access_key) = nixops.ec2_utils.fetch_aws_secret_key(self.access_key_id)
        self._conn = boto.logs.connect_to_region(
            region_name=self.region, aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)

    def _destroy(self):
        if self.state != self.UP: return
        self.connect()
        self.log("destroying cloudwatch log stream ‘{0}’...".format(self.log_stream_name))
        try:
            self._conn.delete_log_stream(log_group_name=self.log_group_name,log_stream_name=self.log_stream_name)
        except  boto.logs.exceptions.ResourceNotFoundException, e:
            self.log("the log group ‘{0}’ or log stream ‘{1}’ was already deleted".format(self.log_group_name,self.log_stream_name))
        with self.depl._state.db:
            self.state = self.MISSING
            self.log_group_name = None
            self.log_stream_name = None
            self.region = None
            self.arn = None

    def lookup_cloudwatch_log_stream(self, log_group_name, log_stream_name, next_token=None):
        if log_stream_name:
         response = self._conn.describe_log_streams(log_group_name=log_group_name,
           log_stream_name_prefix=log_stream_name,next_token=next_token)
         if 'logStreams' in response:
          for log_stream in response['logStreams']:
              if log_stream_name == log_stream['logStreamName']:
                  return True, log_stream['arn']
         if 'nextToken' in response:
             self.lookup_cloudwatch_log_group(log_group_name=log_group_name,
              log_stream_name=log_stream_name,next_token=response['nextToken'])
        return False, None

    def create_after(self, resources, defn):
        # FIXME can be improved to check that we only need to wait for
        # the needed Log Groups to be created and not all Log Groups resources
        return {r for r in resources if
                isinstance(r, nixops.resources.cloudwatch_log_group.CloudWatchLogGroupState)}

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set ‘accessKeyId’, $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        if self.state == self.UP and (self.log_stream_name != defn.config['name'] or
         self.log_group_name != defn.config['logGroupName'] or self.region != defn.config['region']):
            self.log("cloudwatch log stream definition changed, recreating...")
            self._destroy()
            self._conn = None

        self.region = defn.config['region']
        self.connect()
        exist, arn = self.lookup_cloudwatch_log_stream(log_group_name=self.log_group_name,
         log_stream_name=self.log_stream_name)

        if self.arn == None or not exist:
            self.log("creating cloudwatch log stream ‘{0}’ under log group ‘{1}’...".format(defn.config['name'],defn.config['logGroupName']))
            log_group = self._conn.create_log_stream(
             log_stream_name=defn.config['name'],log_group_name=defn.config['logGroupName'])
            exist, arn = self.lookup_cloudwatch_log_stream(log_group_name=defn.config['logGroupName'],
             log_stream_name=defn.config['name'])

        with self.depl._state.db:
            self.state = self.UP
            self.log_stream_name = defn.config['name']
            self.log_group_name = defn.config['logGroupName']
            self.region = defn.config['region']
            self.arn = arn

    def destroy(self, wipe=False):
        self._destroy()
        return True
