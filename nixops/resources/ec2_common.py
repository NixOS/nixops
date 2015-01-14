import socket
import getpass
import nixops.util
import nixops.resources

class EC2CommonState():

    def _retry(self, fun, **kwargs):
        return nixops.ec2_utils.retry(fun, logger=self, **kwargs)

    tags = nixops.util.attr_property("ec2.tags", {}, 'json')

    def get_common_tags(self):
        return {'CharonNetworkUUID': self.depl.uuid,
                'CharonMachineName': self.name,
                'CharonStateFile': "{0}@{1}:{2}".format(getpass.getuser(), socket.gethostname(), self.depl._db.db_file)}

    def update_tags(self, id, user_tags={}, check=False):
        tags = {'Name': "{0} [{1}]".format(self.depl.description, self.name)}
        tags.update(user_tags)
        tags.update(self.get_common_tags())

        if tags != self.tags or check:
            # FIXME: handle removing tags.
            self._retry(lambda: self._conn.create_tags([id], tags))
            self.tags = tags
