# -*- coding: utf-8 -*-

# Automatic provisioning of AWS SNS topics.

import boto
import boto.sns
import nixops.util
import nixops.resources
import nixops.ec2_utils
from xml.etree import ElementTree

class SNSTopicDefinition(nixops.resources.ResourceDefinition):
    """Definition of an SNS topic."""

    @classmethod
    def get_type(cls):
        return "sns-topic"

    @classmethod
    def get_resource_type(cls):
        return "snsTopics"

    def show_type(self):
        return "{0}".format(self.get_type())


class SNSTopicState(nixops.resources.ResourceState):
    """State of an SNS topic."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    topic_name = nixops.util.attr_property("ec2.topicName", None)
    access_key_id = nixops.util.attr_property("ec2.accessKeyId", None)
    display_name = nixops.util.attr_property("ec2.topicDisplayName", None)
    region = nixops.util.attr_property("ec2.region", None)
    policy = nixops.util.attr_property("ec2.topicPolicy", None)
    arn = nixops.util.attr_property("ec2.topicARN", None)
    subscriptions = nixops.util.attr_property("ec2.topicSubscriptions", [],'json')

    @classmethod
    def get_type(cls):
        return "sns-topic"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._conn = None

    def show_type(self):
        s = super(SNSTopicState, self).show_type()
        if self.region: s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return self.topic_name

    def prefix_definition(self, attr):
        return {('resources', 'snsTopics'): attr}

    def get_physical_spec(self):
        return {'arn': self.arn}

    def get_definition_prefix(self):
        return "resources.snsTopics."

    def connect(self):
        if self._conn: return
        assert self.region
        (access_key_id, secret_access_key) = nixops.ec2_utils.fetch_aws_secret_key(self.access_key_id)
        self._conn = boto.sns.connect_to_region(
            region_name=self.region, aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)

    def _destroy(self):
        if self.state != self.UP: return
        self.connect()
        self.log("destroying SNS topic ‘{0}’...".format(self.topic_name))
        self._conn.delete_topic(self.arn)
        with self.depl._state.db:
            self.state = self.MISSING
            self.topic_name = None
            self.region = None
            self.policy = None
            self.arn = None

    def topic_exists(self,arn):
        response = self._conn.get_all_topics()
        topics = response['ListTopicsResponse']['ListTopicsResult']['Topics']
        current_topics = []
        if len(topics) > 0:
            for topic in topics:
                topic_arn = topic['TopicArn']
                current_topics.append(topic_arn)
            if arn in current_topics:
                return True
        return False

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set ‘accessKeyId’, $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        arn = self.arn
        if self.state == self.UP and (self.topic_name != defn.config['name'] or self.region != defn.config['region']):
            self.log("topic definition changed, recreating...")
            self._destroy()
            self._conn = None

        self.region = defn.config['region']
        self.connect()

        if self.arn == None or not self.topic_exists(arn=self.arn):
            self.log("creating SNS topic ‘{0}’...".format(defn.config['name']))
            topic = self._conn.create_topic(defn.config['name'])
            arn = topic.get('CreateTopicResponse').get('CreateTopicResult')['TopicArn']

        if defn.config['displayName'] != None:
            self._conn.set_topic_attributes(topic=arn,attr_name="DisplayName",attr_value=defn.config['displayName'])

        if defn.config['policy'] != "":
            policy = self._conn.set_topic_attributes(topic=arn,attr_name="Policy",attr_value=defn.config['policy'])

        current_subscribers, current_subscriptions_arns = self.get_current_subscribers(arn=arn)

        if len(defn.config['subscriptions']) > 0:
            for subscriber in defn.config['subscriptions']:
                protocol = subscriber['protocol']
                endpoint = subscriber['endpoint']
                if endpoint not in current_subscribers:
                    self.log("adding SNS subscriber with endpoint '{0}'...".format(endpoint))
                    self._conn.subscribe(topic=arn,protocol=protocol,endpoint=endpoint)

        defn_endpoints = self.get_defn_endpoints(defn)
        if len(defn_endpoints) > 0:
            for subscriber_endpoint, subscriber_arn in current_subscriptions_arns.items():
                if subscriber_endpoint not in defn_endpoints:
                    self.log("removing SNS subscriber with endpoint '{0}'...".format(subscriber_endpoint))
                    if subscriber_arn != "PendingConfirmation": 
                     self._conn.unsubscribe(subscription=subscriber_arn)

        with self.depl._state.db:
            self.state = self.UP
            self.topic_name = defn.config['name']
            self.display_name = defn.config['displayName']
            self.policy = defn.config['policy']
            self.arn = arn
            self.subscriptions = defn.config['subscriptions']

    def get_current_subscribers(self,arn):
        response = self._conn.get_all_subscriptions_by_topic(topic=arn)
        current_subscribers = response['ListSubscriptionsByTopicResponse']['ListSubscriptionsByTopicResult']['Subscriptions']
        current_endpoints = []
        current_subscriptions_arns = {}
        if len(current_subscribers) > 0:
         for subscriber in current_subscribers:
             current_endpoints.append(subscriber['Endpoint'])
             current_subscriptions_arns[subscriber['Endpoint']]=subscriber['SubscriptionArn']
        return current_endpoints,current_subscriptions_arns

    def get_defn_endpoints(self,defn):
        defn_endpoints = []
        if len(defn.config['subscriptions']) > 0:
            for subscriber in defn.config['subscriptions']:
                defn_endpoints.append(subscriber['endpoint'])
        return defn_endpoints

    def destroy(self, wipe=False):
        self._destroy()
        return True
