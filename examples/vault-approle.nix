
{vaultToken ? "xxxxxxxxxxx"
, vaultAddress ? "https://vault.nagato.com:8200"
, ...
}:
{
  network.description = "vault test";
  resources.vaultApprole.vault-test =
    {resources, ...}:
    {
      inherit vaultAddress vaultToken;
      bindSecretId = true;
      tokenNumUses = 5;
      roleName = "test123";
      tokenBoundCidrs = [ "100.110.120.130/32"];
      policies = [ "admin" "dovah" "${resources.vaultPolicy.vault-policy.name}" ];
    };

  resources.vaultPolicy.vault-policy =
  { resources, ... }:
  {
    inherit vaultAddress vaultToken;
    name = "nixopsPolicy";
    policies = [{
      path = "${resources.vaultKVSecretEngine.kvengine.name}/*";
      capabilities = [ "create" "read" "list"];
     }
     {
      path = "othersecretengine/*";
      capabilities = [ "delete" "list" ];
     }];
  };
  resources.vaultKVSecretEngine.kvengine = {
    inherit vaultAddress vaultToken;
    name = "nixopsSecrets";
    description = "kv 2 secret engine provisioned with nixops";
    secrets = [{
      path = "test1";
      data = [{
        key = "content";
        value = "some content";
      }
      {
        key = "other";
        value = "value2";
      }];
    }
    {
      path = "test2";
      data = [{
        key = "key1";
        value = "something somehting";
      }
      {
        key = "key2";
        value = "test";
      }];
    }];
  };
}