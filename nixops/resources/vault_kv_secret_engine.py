# -*- coding: utf-8 -*-

# Automatic provisioning of Hashicorp Vault kv2 secret backends

import json

import nixops.util
import nixops.resources
import nixops.vault_common
from nixops.diff import Diff, Handler
from nixops.state import StateDict

class VaultKVSecretEngineDefinition(nixops.resources.ResourceDefinition):
    """Definition of a vault kv (2) secret engine."""

    @classmethod
    def get_type(cls):
        return "vault-kv-secret-engine"

    @classmethod
    def get_resource_type(cls):
        return "vaultKVSecretEngine"

    def show_type(self):
        return "{0}".format(self.get_type())

class VaultKVSecretEngineState(nixops.resources.DiffEngineResourceState):
    """State of a vault kv secret engine."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    _reserved_keys = ['vaultToken']

    @classmethod
    def get_type(cls):
        return "vault-kv-secret-engine"

    def __init__(self, depl, name, id):
        nixops.resources.DiffEngineResourceState.__init__(self, depl, name, id)
        self.handle_create_engine = Handler(['name', 'vaultAddress', 'type', 'local', 'sealWrap', 'version', 'forceNoCache'],
                                            handle=self.realize_create_engine)
        self.handle_update_engine = Handler(['maxLeaseTtl', 'listingVisibility', 'passthroughRequestHeaders', 'defaultLeaseTtl', 'allowedResponseHeaders', 'auditNonHmacRequestKeys', 'auditNonHmacResponseKeys', 'description'],
                                            after=[self.handle_create_engine],
                                            handle=self.realize_update_engine)
        self.handle_update_policy = Handler(['secrets'],
                                            after=[self.handle_update_engine, self.handle_create_engine], 
                                            handle=self.realize_create_secrets)

    def show_type(self):
        s = super(VaultKVSecretEngineState, self).show_type()
        return s

    def get_definition_prefix(self):
        return "resources.vaultKVSecretEngine."

    def realize_create_engine(self, allow_recreate):
        config = self.get_defn()

        self._state['name'] = config['name']
        self._state['vaultAddress'] = config['vaultAddress']
        self._state['vaultToken'] = config['vaultToken']

        self.log("Creating kv secret engine: `{0}`...".format(self._state['name']))

        data = {
            "type": config['type'],
            "local": config['local'],
            "seal_wrap": config['sealWrap'],
            "options": {
                "version": config["version"]
            },
            "config": {
                "force_no_cache": config["forceNoCache"], 
            }
        }
        r = nixops.vault_common.vault_post(
                config['vaultToken'], config['vaultAddress'],
                self._state['name'], data, "kv2engine")
        if r.status_code != 204:
            raise Exception("{} {}, {}".format(
                r.status_code, r.reason, r.json()))

        with self.depl._db:
            self.state = self.STARTING
            self._state['type'] = config['type']
            self._state['local'] = config['local']
            self._state['sealWrap'] = config['sealWrap']
            self._state['forceNoCache'] = config['forceNoCache']
            self._state['version'] = config['version']

    def realize_create_secrets(self, allow_recreate):
        config = self.get_defn()

        self.log("Populating `{}` engine with secrets...".format(self._state['name']))

        for i in config['secrets']:
            data = {
                "data": {
                    d['key']: d['value'] for d in i['data']
                }
            }
            metadata = {
                "max_versions": i['maxVersions']
            }
            r = nixops.vault_common.vault_post(
                    self._state['vaultToken'], self._state['vaultAddress'],
                    self._state['name'] + "/data/" + i['path'], data, "secret")
            if r.status_code != 200:
                raise Exception("{} {}, {}".format(
                    r.status_code, r.reason, r.json()))
            r = nixops.vault_common.vault_post(
                    self._state['vaultToken'], self._state['vaultAddress'],
                    self._state['name'] + "/metadata/" + i['path'], metadata, "secret")
            if r.status_code != 204:
                raise Exception("{} {}, {}".format(
                    r.status_code, r.reason, r.json()))
        with self.depl._db:
            self._state['secrets'] = config['secrets']

    def realize_update_engine(self, allow_recreate):
        config = self.get_defn()

        self.log("Updating kv secret engine: `{0}`...".format(self._state['name']))
        data = {
            "default_lease_ttl": config['defaultLeaseTtl'],
            "max_lease_ttl": config['maxLeaseTtl'],
            "description": config['description'],
            "audit_non_hmac_request_keys": config['auditNonHmacRequestKeys'],
            "audit_non_hmac_response_keys": config['auditNonHmacResponseKeys'],
            "listing_visibility": config['listingVisibility'],
            "passthrough_request_headers": config['passthroughRequestHeaders'],
            "allowed_response_headers": config['allowedResponseHeaders']
        }

        r = nixops.vault_common.vault_post(
                config['vaultToken'], config['vaultAddress'],
                self._state['name'] + '/tune', data, "kv2engine")
        if r.status_code != 204:
            raise Exception("{} {}, {}".format(
                r.status_code, r.reason, r.json()))

        with self.depl._db:
            self.state = self.UP
            self._state['defaultLeaseTtl'] = config['defaultLeaseTtl']
            self._state['maxLeaseTtl'] = config['maxLeaseTtl']
            self._state['description'] = config['description']
            self._state['auditNonHmacRequestKeys'] = config['auditNonHmacRequestKeys']
            self._state['auditNonHmacResponseKeys'] = config['auditNonHmacResponseKeys']
            self._state['listingVisibility'] = config['listingVisibility']
            self._state['passthroughRequestHeaders'] = config['passthroughRequestHeaders']
            self._state['allowedResponseHeaders'] = config['allowedResponseHeaders']

    def _check(self):
        if self._state['name'] is None:
            return

        r = nixops.vault_common.vault_get(
                self._state['vaultToken'], self._state['vaultAddress'],
                self._state['name'] + "/tune", "kv2engine")
        #TODO: should be 404 as the others but i get this 
        # error when checking for engine after manual deletion
        # {u'errors': [u'cannot fetch sysview for path "testSecret/"']}
        if r.status_code == 400:
            self.warn("kv secret engine '{0}' was deleted from outside nixops,"
                      " it needs to be recreated...".format(self._state['name']))
            self.destroy()
        elif r.status_code != 200:
            raise Exception("{} {}, {}".format(
                r.status_code, r.reason, r.json()))

    def _destroy(self):
        if self.state == self.MISSING: return
        self.log("deleting KV Secret Engine `{0}`...".format(self._state['name']))
        r = nixops.vault_common.vault_delete(
                self._state['vaultToken'], self._state['vaultAddress'], self._state['name'], "kv2engine")
        if r.status_code == 204:
            pass
        else:
            raise Exception(r.json())

        with self.depl._db:
            self.state = self.MISSING
            self._state['secrets'] = None
            self._state['vaultToken'] = None
            self._state['vaultAddress'] = None
            self._state['name'] = None
            self._state['type'] = None
            self._state['local'] = None
            self._state['sealWrap'] = None
            self._state['forceNoCache'] = None
            self._state['version'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
