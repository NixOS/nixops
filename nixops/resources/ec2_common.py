import socket
import getpass

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

    def plan(self, defn):
        if hasattr(self, '_state'):
            diff_engine = self.setup_diff_engine(defn.config)
            diff_engine.plan(show=True)
        else:
            self.warn("resource type {} doesn't implement a plan operation".format(self.get_type()))

    def setup_diff_engine(self, config):
        diff_engine = Diff(depl=self.depl, logger=self.logger,
                           config=config, state=self._state,
                           res_type=self.get_type())
        diff_engine.set_reserved_keys(self._reserved_keys)
        diff_engine.set_handlers(self.get_handlers())
        return diff_engine

    def get_handlers(self):
        return [getattr(self,h) for h in dir(self) if isinstance(getattr(self,h), Handler)]

    def get_defn(self):
        return self.depl.definitions[self.name].config
