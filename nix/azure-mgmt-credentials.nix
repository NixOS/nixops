lib: name:
with lib;
{

  subscriptionId = mkOption {
    default = "";
    example = "f1ce4500-ab06-495a-8d59-a7cfe9e46dae";
    type = types.str;
    description = ''
      The Azure Subscription ID. If left empty, it defaults to the
      contents of the environment variable <envar>AZURE_SUBSCRIPTION_ID</envar>.
    '';
  };

  authority = mkOption {
    default = "";
    example = "https://login.windows.net/ACTIVE_DIRECTORY_TENANT.onmicrosoft.com";
    type = types.str;
    description = ''
      The Azure Authority URL. If left empty, it defaults to the
      contents of the environment variable <envar>AZURE_AUTHORITY_URL</envar>.
    '';
  };

  user = mkOption {
    default = "";
    example = "username@ACTIVE_DIRECTORY_TENANT.onmicrosoft.com";
    type = types.str;
    description = ''
      The Azure User. If left empty, it defaults to the
      contents of the environment variable <envar>AZURE_USER</envar>.
    '';
  };

  password = mkOption {
    default = "";
    example = "password";
    type = types.str;
    description = ''
      The Azure Password. If left empty, it defaults to the
      contents of the environment variable <envar>AZURE_PASSWORD</envar>.
    '';
  };

}