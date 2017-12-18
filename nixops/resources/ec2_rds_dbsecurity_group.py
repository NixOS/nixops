import boto3
import botocore.exceptions

import nixops.util
import nixops.resources
import nixops.ec2_utils

class EC2RDSDbSecurityGroupDefinition(nixops.resources.ResourceDefinition):

    @classmethod
    def get_type(cls):
        return "ec2-rds-dbsecurity-group"

    @classmethod
    def get_resource_type(cls):
        return "rdsDbSecurityGroups"

    def show_type(self):
        return "{0}".format(self.get_type())

class EC2RDSDbSecurityGroupState(nixops.resources.ResourceState):

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    region = nixops.util.attr_property("region", None)
    security_group_name = nixops.util.attr_property("securityGroupName", None)
    security_group_description = nixops.util.attr_property("securityGroupDescription", None)
    rules = nixops.util.attr_property("rules", [], "json")

    @classmethod
    def get_type(cls):
        return "ec2-rds-dbsecurity-group"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._client = None

    def show_type(self):
        s = super(EC2RDSDbSecurityGroupState, self).show_type()
        return "{0} [{1}]".format(s, self.region)

    @property
    def resource_id(self):
        return self.security_group_name

    def get_client(self):
        assert self.region
        if self._client is not None:
            return self._client
        (access_key_id, secret_access_key) = nixops.ec2_utils.fetch_aws_secret_key(self.access_key_id)
        self._client = boto3.session.Session().client(service_name='rds', region_name=self.region,
                                                      aws_access_key_id=access_key_id,
                                                      aws_secret_access_key=secret_access_key)
        return self._client

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.access_key_id = defn.config["accessKeyId"] or nixops.ec2_utils.get_access_key_id()

        self.region  = defn.config["region"]

        if self.state == self.MISSING:
            self.log("creating rds db security group {}".format(defn.config['name']))
            self.get_client().create_db_security_group(DBSecurityGroupName=defn.config['name'],
                    DBSecurityGroupDescription=defn.config['description'])

            with self.depl._db:
                self.state = self.UP
                self.security_group_name = defn.config['name']
                self.security_group_description = defn.config['description']

        rules_to_remove = [r for r in self.rules if r not in defn.config['rules'] ]
        rules_to_add = [r for r in defn.config['rules'] if r not in self.rules]

        for rule in rules_to_remove:
            kwargs = self.process_rule(rule)
            self.get_client().revoke_db_security_group_ingress(**kwargs)

        for rule in rules_to_add:
            kwargs = self.process_rule(rule)
            self.get_client().authorize_db_security_group_ingress(**kwargs)

        with self.depl._db:
            self.rules = defn.config['rules']

    def process_rule(self, config):
        # FIXME do more checks before passing the args to the boto api call
        args = dict()
        args['DBSecurityGroupName'] = self.security_group_name
        args['CIDRIP'] = config.get('cidrIp', None)
        args['EC2SecurityGroupName'] = config.get('securityGroupName', None)
        args['EC2SecurityGroupId'] = config.get('securityGroupId', None)
        args['EC2SecurityGroupOwnerId'] = config.get('securityGroupOwnerId', None)
        return { attr : args[attr] for attr in args if args[attr] is not None }

    def destroy(self, wipe=True):
        if self.state != self.UP:
            return True
        self.log("destroying rds db security group {}".format(self.security_group_name))
        try:
            self.get_client().delete_db_security_group(DBSecurityGroupName=self.security_group_name)
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == 'DBSecurityGroupNotFound':
                self.warn("rds security group {} already deleted".format(self.security_group_name))
            else:
                raise error

        with self.depl._db:
            self.state = self.MISSING
            self.security_group_name = None
            self.security_group_description = None
            self.rules = None
        return True
