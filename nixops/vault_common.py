import os
import requests

TIMEOUT = 5

def initializeVault(vault_token=None):
    if not vault_token:
        vault_token = os.environ.get('VAULT_TOKEN')
    if not vault_token:
        raise Exception(
            "please set the vault token options (or the environment variables VAULT_TOKEN)")
    return vault_token

def remote_path(base, path, path_type):
    if path_type == "approle":
        return base + '/v1/auth/approle/role/' + path
    elif path_type == "policy":
        return base + "/v1/sys/policy/" + path
    elif path_type == "kv2engine":
        return base + "/v1/sys/mounts/" + path
    elif path_type == "secret":
        return base + "/v1/" + path
    else:
        raise

def vault_get(vault_token, vault_address, path, path_type="approle"):
    try:
        header = {"X-Vault-Token": vault_token.rstrip()}
        remote_endpoint = remote_path(vault_address, path, path_type)
        r = requests.get(remote_endpoint, headers=header, timeout=TIMEOUT)
    except requests.exceptions.RequestException as e:
        raise e.args[0]
    return r

def vault_post(vault_token, vault_address, path, data, path_type="approle"):
    try:
        header = {"X-Vault-Token": vault_token.rstrip()}
        remote_endpoint = remote_path(vault_address, path, path_type)
        r = requests.post(remote_endpoint, headers=header,
                          json=data, timeout=TIMEOUT)
    except requests.exceptions.RequestException as e:
        raise e.args[0]
    return r

def vault_delete(vault_token, vault_address, path, path_type="approle"):
    try:
        header = {"X-Vault-Token": vault_token.rstrip()}
        remote_endpoint = remote_path(vault_address, path, path_type)
        r = requests.delete(remote_endpoint, headers=header, timeout=TIMEOUT)
    except requests.exceptions.RequestException as e:
        raise e.args[0]
    return r
