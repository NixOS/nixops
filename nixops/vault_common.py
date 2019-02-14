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

def approle_path(base, path):
    return base + '/v1/auth/approle/role/' + path

def vault_get(vault_token, vault_address, path):
    try:
        header = {"X-Vault-Token": vault_token}
        remote_endpoint = approle_path(vault_address, path)
        r = requests.get(remote_endpoint, headers=header, timeout=TIMEOUT)
    except requests.exceptions.RequestException as e:
        raise e.args[0]
    return r

def vault_post(vault_token, vault_address, path, data):
    try:
        header = {"X-Vault-Token": vault_token}
        remote_endpoint = approle_path(vault_address, path)
        r = requests.post(remote_endpoint, headers=header,
                          json=data, timeout=TIMEOUT)
    except requests.exceptions.RequestException as e:
        raise e.args[0]
    return r

def vault_delete(vault_token, vault_address, path):
    try:
        header = {"X-Vault-Token": vault_token}
        remote_endpoint = approle_path(vault_address, path)
        r = requests.delete(remote_endpoint, headers=header, timeout=TIMEOUT)
    except requests.exceptions.RequestException as e:
        raise e.args[0]
    return r
