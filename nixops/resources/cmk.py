# -*- coding: utf-8 -*-

# Automatic provisioning of AWS CMK.
import os
import boto3
import botocore

import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
import nixops.ec2_utils
from nixops.state import StateDict
from nixops.diff import Diff, Handler

class CMKDefinition(nixops.resources.ResourceDefinition):
    """Definition of a CMK."""

    @classmethod
    def get_type(cls):
        return "cmk"

    @classmethod
    def get_resource_type(cls):
        return "cmk"

    def show_type(self):
        return "{0}".format(self.get_type())


class CMKState(nixops.resources.DiffEngineResourceState, EC2CommonState):
    """State of a CMK."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ["keyId"]

    @classmethod
    def get_type(cls):
        return "cmk"

    def __init__(self, depl, name, id):
        nixops.resources.DiffEngineResourceState.__init__(self, depl, name, id)
        self.keyId = self._state.get('keyId', None)
        self.handle_create = Handler(['deletionWaitPeriod', 'origin', 'region', 'customKeyStoreId'],
                                     handle=self.realize_create_cmk)
        self.handle_description = Handler(['description'], after=[self.handle_create],
                                          handle=self.realize_update_description)
        self.handle_policy = Handler(['policy'], after=[self.handle_create], handle=self.realize_policy)
        self.handle_alias = Handler(['alias'], after=[self.handle_create], handle=self.realize_update_alias)
        self.handle_import_custom_key = Handler(['externalKey'], after=[self.handle_create],
                                                handle=self.realize_import_custom_key)
        self.handle_tag_update = Handler(['tags'], after=[self.handle_create], handle=self.realize_update_tag)

    def show_type(self):
        s = super(CMKState, self).show_type()
        region = self._state.get('region', None)
        if region: s = "{0} [{1}]".format(s, region)
        return s

    @property
    def resource_id(self):
        return self._state.get('keyId', None)

    def prefix_definition(self, attr):
        return {('resources', 'cmk'): attr}

    def get_physical_spec(self):
        return { 'cmkId': self._state.get('keyId', None)}

    def get_definition_prefix(self):
        return "resources.cmk."

    def realize_create_cmk(self, allow_recreate):
        """Handle both create and recreate of the cmk resource """
        config = self.get_defn()
        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("cmk {} definition changed and it needs to be recreated "
                                "use --allow-recreate if you want to create a new one".format(self.keyId))
            self.warn("cmk definition changed, recreating...")
            self._destroy()
            self._client = None

        self._state["region"] = config['region']

        self.log("creating cmk under region {0}".format(config['region']))
        args = dict(
            KeyUsage='ENCRYPT_DECRYPT',
            Origin = config['origin'],
        )
        if config['customKeyStoreId']:
            args['CustomKeyStoreId'] = config['customKeyStoreId']
        cmk = self.get_client(service="kms").create_key(**args)
        self.keyId = cmk['KeyMetadata']['KeyId']

        with self.depl._db:
            self.state = self.UP if config['origin'] != "EXTERNAL" else self.STARTING
            self._state["keyId"] = self.keyId
            self._state["region"] = config['region']
            self._state["origin"] = config['origin']
            self._state["deletionWaitPeriod"] = config['deletionWaitPeriod']

    def realize_update_description(self, allow_recreate):
        config = self.get_defn()
        self.get_client(service="kms").update_key_description(KeyId=self.keyId, Description=config['description'])

        with self.depl._db:
            self._state['description'] = config['description']

    def realize_policy(self, allow_recreate):
        config = self.get_defn()
        self.log("updating `{0}` policy...".format(self.keyId))
        self.get_client(service="kms").put_key_policy(KeyId=self.keyId, PolicyName="default", Policy=config['policy'])

        with self.depl._db:
            self._state['policy'] = config['policy']

    def realize_update_tag(self, allow_recreate):
        config = self.get_defn()
        tags = config['tags']
        tags.update(self.get_common_tags())
        self.get_client(service="kms").tag_resource(KeyId=self.keyId, Tags=[{"TagKey": k, "TagValue": tags[k]} for k in tags])

    def realize_update_alias(self, allow_recreate):
        config = self.get_defn()
        # we don't want to have many alias for a key so we delete the old one before creating a new
        if self._state.get('subnetId', None):
            self.get_client(service="kms").delete_alias(AliasName="alias/" + self._state['alias'])
            self.log("updating `{0}` alias...".format(self.keyId))
        else:
            self.log("creating alias for `{0}`...".format(self.keyId))
        self.get_client(service="kms").create_alias(TargetKeyId=self.keyId, AliasName="alias/" + config['alias'])

        with self.depl._db:
            self._state['alias'] = config['alias']

    def realize_import_custom_key(self, allow_recreate):
        config = self.get_defn()
        if config['origin'] != "EXTERNAL":
            raise Exception('"origin" should be set to "EXTERNAL", when providing externalKey options')
        #TODO: work on this
        raise Exception('This is currently not supported!')
        # parameters_for_import = self.get_client(service="kms").get_parameters_for_import(
        #     KeyId=self.keyId,
        #     WrappingAlgorithm=config['externalKey']['wrappingAlgorithm'],
        #     WrappingKeySpec=config['externalKey']['wrappingKeySpec']
        # )
        # self._state['externalKey']['keyMaterial'] = os.urandom(32)

        # some key wrapping logic

        # args = dict(
        #     KeyId=self.keyId,
        #     ImportToken=parameters_for_import['ImportToken'],
        #     EncryptedKeyMaterial=wrappedKey
        # )
        # if config['externalKey']['keyMaterialExpire']:
        #     args['ExpirationModel'] = 'KEY_MATERIAL_EXPIRES'
        #     args['ValidTo'] =
        # else:
        #     args['ExpirationModel'] = 'KEY_MATERIAL_DOES_NOT_EXPIRE'

        # self.get_client(service="kms").import_key_material(**args)
        # with self.depl._db:
            # self.state = self.UP
            # self._state['externalKey'] = config['externalKey']

    def _check(self):
        if self._state.get('keyId', None) is None:
            return
        try:
            cmk = self.get_client(service="kms").describe_key(KeyId=self._state["keyId"])
            print self.get_client(service="kms").list_aliases(KeyId=self._state["keyId"])
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'InvalidKmsID.NotFound':
                self.warn("cmk {0} was deleted from outside nixops,"
                          " it needs to be recreated...".format(self._state["keyId"]))
                self.cleanup_state()
                return
        cmk_state = cmk['KeyMetadata']['KeyState']
        if cmk_state == "PendingImport":
            self.state = self.STARTING
        elif cmk_state == "Enabled":
            return
        elif cmk_state == "Disabled":
            raise Exception("cmk state is {1}, Enable it form the console".format(cmk_state))
        elif cmk_state == "PendingDeletion":
            raise Exception("cmk state is {1}, run a destroy operation to sync the state or cancel the deletion.".format(cmk_state))
        else:
            raise Exception("cmk state is {1}".format(cmk_state))

    def _destroy(self):
        if self.state != self.UP: return
        if self._state['deletionWaitPeriod'] == 0:
            self.warn("`deletionWaitPeriod` for the cmk is set to 0, keeping the key and cleaning the nixops state...")
        else:
            self.get_client(service="kms").delete_alias(AliasName="alias/" + self._state['alias'])
            self.log("scheduling cmk `{0}` deletion to {1} day(s)...".format(self._state['alias'], self._state['deletionWaitPeriod']))
            try:
                self.get_client(service="kms").schedule_key_deletion(
                                            KeyId=self._state['keyId'],
                                            PendingWindowInDays=self._state['deletionWaitPeriod'])
            except botocore.exceptions.ClientError as e:
                # fix this
                if e.response['Error']['Code'] == 'InvalidCmkID.NotFound':
                    self.warn("cmk {0} was already deleted".format(self._state['keyId']))
                else:
                    raise e
        self.cleanup_state()

    def cleanup_state(self):
        with self.depl._db:
            self.state = self.MISSING
            self._state['keyId'] = None
            self._state['region'] = None
            self._state['alias'] = None
            self._state['policy'] = None
            self._state['description'] = None
            self._state['origin'] = None
            self._state['customKeyStoreId'] = None
            self._state['deletionWaitPeriod'] = None
            self._state['externalKey'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
