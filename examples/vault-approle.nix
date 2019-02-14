
{
  network.description = "vault test";
  resources.vaultApprole.vault-test = {
    bindSecretId = true;
    vaultAddress = "https://vault.nagato.com:8200";
    tokenNumUses = 5;
    vaultToken = "xxxxxxxxxxxxxxxxxx";
    roleName = "test123";
    tokenBoundCidrs = [ "100.110.120.130/32"];
    policies = [ "admin" "dovah" ];
  };
}


