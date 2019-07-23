from __future__ import absolute_import

import getpass
import socket

import boto3
from typing import Callable, Dict, Mapping, Optional

import nixops.ec2_utils
import nixops.resources
import nixops.util
from . import ResourceState
from ..ec2_utils import key_value_to_ec2_key_value


class EC2CommonState(ResourceState):

    COMMON_EC2_RESERVED = ['accessKeyId', 'ec2.tags']

    def _retry(self, fun, **kwargs):
        return nixops.ec2_utils.retry(fun, logger=self, **kwargs)

    tags = nixops.util.attr_property("ec2.tags", {}, 'json')

    def get_common_tags(self):
        # type: () -> Dict[str, str]
        tags = {'CharonNetworkUUID': self.depl.uuid,
                'CharonMachineName': self.name,
                'CharonStateFile': "{0}@{1}:{2}".format(getpass.getuser(), socket.gethostname(), self.depl._db.db_file)}
        if self.depl.name:
            tags['CharonNetworkName'] = self.depl.name
        return tags

    def get_default_name_tag(self):
        # type: () -> str
        return "{0} [{1}]".format(self.depl.description, self.name)

    def update_tags_using(self, updater, user_tags=None, check=False):
        # type: (Callable[[Mapping[str, str]], None], Optional[Mapping[str, str]], bool) -> None

        if user_tags is None:
            user_tags = {}

        tags = {'Name': self.get_default_name_tag()}
        tags.update(user_tags)
        tags.update(self.get_common_tags())

        if tags != self.tags or check:
            updater(tags)
            self.tags = tags

    def update_tags(self, session, id, user_tags=None, check=False):
        # type: (boto3.Session, str, Optional[Dict[str, str]], bool) -> None

        if user_tags is None:
            user_tags = {}

        def updater(tags):
            # type: (Mapping[str, str]) -> None

            ec2 = session.client('ec2')

            # FIXME: handle removing tags.
            self._retry(lambda: ec2.create_tags(Resources=[id], Tags=key_value_to_ec2_key_value(tags)))

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
        (access_key_id, secret_access_key) = nixops.ec2_utils.fetch_aws_secret_key(self.access_key_id)
        self._client = boto3.session.Session().client(
            service_name=service,
            region_name=self._state['region'],
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key)
        return self._client

    def reset_client(self):
        self._client = None
