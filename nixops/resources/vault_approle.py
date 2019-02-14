import json

import nixops.util
import nixops.resources
import nixops.vault_common


class VaultApproleDefinition(nixops.resources.ResourceDefinition):
    """Definition of a Vault Approle"""

    @classmethod
    def get_type(cls):
        return "vault-approle"

    @classmethod
    def get_resource_type(cls):
        return "vaultApprole"

    def show_type(self):
        return "{0}".format(self.get_type())


class VaultApproleState(nixops.resources.ResourceState):
    """State of a Vault Approle"""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    vault_token = nixops.util.attr_property("vaultToken", None)
    vault_address = nixops.util.attr_property("vaultAddress", None)
    role_name = nixops.util.attr_property("roleName", None)
    bind_secret_id = nixops.util.attr_property("bindSecretId", None)
    policies = nixops.util.attr_property("policies", [], 'json')
    secret_id_bound_cidrs = nixops.util.attr_property("secretIdBoundCidrs", [], 'json')
    token_bound_cidrs = nixops.util.attr_property("tokenBoundCidrs", [], 'json')
    secret_id_num_uses = nixops.util.attr_property("secretIdNumUses", None)
    secret_id_ttl = nixops.util.attr_property("secretIdTtl", None)
    token_num_uses = nixops.util.attr_property("tokenNumUses", None)
    token_max_ttl = nixops.util.attr_property("tokenMaxTtl", None)
    token_ttl = nixops.util.attr_property("tokenTtl", None)
    enable_local_secret_ids = nixops.util.attr_property("enableLocalSecretIds", None)
    cidr_list = nixops.util.attr_property("cidrList", [], 'json')
    token_type = nixops.util.attr_property("tokenType", None)
    period = nixops.util.attr_property("period", None)
    role_id = nixops.util.attr_property("roleId", None)
    secret_id = nixops.util.attr_property("secretId", None)

    @classmethod
    def get_type(cls):
        return "vault-approle"

    def show_type(self):
        s = super(VaultApproleState, self).show_type()
        return s

    @property
    def resource_id(self):
        return nixops.vault_common.approle_path(self.vault_address, self.role_name) if self.role_name else None

    def get_definition_prefix(self):
        return "resources.vaultApprole."

    def get_physical_spec(self):
        physical = {}
        if self.role_name:
            physical['url'] = nixops.vault_common.approle_path(
                self.vault_address, self.role_name)
            physical['roleId'] = self.role_id
            physical['secretId'] = self.secret_id
        return physical

    def prefix_definition(self, attr):
        return {('resources', 'vaultApprole'): attr}

    def _check(self):
        if self.role_id is None:
            return

        r = nixops.vault_common.vault_get(
                self.vault_token, self.vault_address,
                self.role_name + '/role-id')

        if r.status_code == 404:
            self.warn("Approle '{0}' was deleted from outside nixops,"
                      " it needs to be recreated...".format(self.role_name))
            self.destroy()
        elif r.status_code != 200:
            raise Exception("{} {}, {}".format(
                r.status_code, r.reason, r.json()))

    def _get_role_id_secret_id(self, defn):
        r = nixops.vault_common.vault_get(
                self.vault_token, self.vault_address,
                self.role_name + '/role-id')

        if r.status_code == 200:
            self.role_id = r.json()['data']['role_id']
        else:
            raise Exception("{} {}, {}".format(
                r.status_code, r.reason, r.json()))

        if defn.config['bindSecretId'] and self.state != self.UP:
            data = {
                "cidr_list": defn.config['cidrList'],
                "token_bound_cidrs": defn.config['tokenBoundCidrs']
            }
            r = nixops.vault_common.vault_post(
                self.vault_token, self.vault_address,
                self.role_name + '/secret-id', data)

            if r.status_code == 200:
                self.secret_id = r.json()['data']['secret_id']
            else:
                raise Exception("{} {}, {}".format(
                    r.status_code, r.reason, r.json()))
        # TODO: Maybe enable setting custom role ID and custom secret ID.

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.vault_address = defn.config['vaultAddress']
        self.vault_token = defn.config['vaultToken']
        self.role_name = defn.config['roleName']

        self.log("Creating Approle '{}' at {} ...".format(
            self.role_name, self.vault_address))

        data = {
            "token_ttl": defn.config['tokenTtl'],
            "token_max_ttl": defn.config['tokenMaxTtl'],
            "policies": defn.config['policies'],
            "secret_id_bound_cidrs": defn.config['secretIdBoundCidrs'],
            "token_bound_cidrs": defn.config['tokenBoundCidrs'],
            "secret_id_num_uses": defn.config['secretIdNumUses'],
            "secret_id_ttl": defn.config['secretIdTtl'],
            "token_num_uses": defn.config['tokenNumUses'],
            "period": defn.config['period'],
            "enable_local_secret_ids": defn.config['enableLocalSecretIds'],
            "bind_secret_id": defn.config['bindSecretId'],
            "token_type": defn.config['tokenType']
        }
        r = nixops.vault_common.vault_post(
                self.vault_token, self.vault_address,
                self.role_name, data)

        if r.status_code != 204:
            raise Exception("{} {}, {}".format(
                r.status_code, r.reason, r.json()))

        self._get_role_id_secret_id(defn)

        with self.depl._db:
            self.state = self.UP
            self.role_name = defn.config['roleName']
            self.vault_address = defn.config['vaultAddress']
            self.bind_secret_id = defn.config['bindSecretId']
            self.secret_id_num_uses = defn.config['secretIdNumUses']
            self.secret_id_ttl = defn.config['secretIdTtl']
            self.token_num_uses = defn.config['tokenNumUses']
            self.token_max_ttl = defn.config['tokenMaxTtl']
            self.token_ttl = defn.config['tokenTtl']
            self.period = defn.config['period']
            self.enable_local_secret_ids = defn.config['enableLocalSecretIds']
            self.token_type = defn.config['tokenType']
            self.secret_id_bound_cidrs = defn.config['secretIdBoundCidrs']
            self.token_bound_cidrs = defn.config['tokenBoundCidrs']
            self.policies = defn.config['policies']
            self.cidr_list = defn.config['cidrList']

    def _destroy(self):
        if self.state != self.UP:
            return
        self.log("deleting vault Approle {0} ...".format(self.role_name))
        r = nixops.vault_common.vault_delete(
                self.vault_token, self.vault_address, self.role_name)
        if r.status_code == 204:
            return True
        else:
            raise Exception(r.json())

    def destroy(self, wipe=False):
        self._destroy()
        return True
