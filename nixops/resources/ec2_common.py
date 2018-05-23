import socket
import getpass

import boto3

import nixops.util
import nixops.resources
from nixops.diff import Diff, Handler

class EC2CommonState():

    COMMON_EC2_RESERVED = ['accessKeyId', 'ec2.tags']

    def _retry(self, fun, **kwargs):
        return nixops.ec2_utils.retry(fun, logger=self, **kwargs)

    tags = nixops.util.attr_property("ec2.tags", {}, 'json')

    def get_common_tags(self):
        tags = {'CharonNetworkUUID': self.depl.uuid,
                'CharonMachineName': self.name,
                'CharonStateFile': "{0}@{1}:{2}".format(getpass.getuser(), socket.gethostname(), self.depl._db.db_file)}
        if self.depl.name:
            tags['CharonNetworkName'] = self.depl.name
        return tags

    def get_default_name_tag(self):
        return "{0} [{1}]".format(self.depl.description, self.name)

    def update_tags_using(self, updater, user_tags={}, check=False):
        tags = {'Name': self.get_default_name_tag()}
        tags.update(user_tags)
        tags.update(self.get_common_tags())

        if tags != self.tags or check:
            updater(tags)
            self.tags = tags

    def update_tags(self, id, user_tags={}, check=False):

        def updater(tags):
            # FIXME: handle removing tags.
            self._retry(lambda: self._conn.create_tags([id], tags))

        self.update_tags_using(updater, user_tags=user_tags, check=check)

    def get_client(self, service="ec2"):
        '''
        Generic method to get a cached AWS client or create it.
        '''
        new_access_key_id = (self.get_defn()['accessKeyId'] if self.depl.definitions else None) \
                            or nixops.ec2_utils.get_access_key_id()
        if new_access_key_id is not None:
            self.access_key_id = new_access_key_id
        if self.access_key_id is None:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")
        if hasattr(self, '_client'):
            if self._client: return self._client
        assert self._state['region']
        creds = nixops.ec2_utils.fetch_aws_secret_key(self.access_key_id)
        self._client = boto3.session.Session().client(
            service_name=service,
            region_name=self._state['region'],
            **creds)
        return self._client

    def reset_client(self):
        self._client = None
