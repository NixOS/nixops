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

  identifierUri = mkOption {
    default = "https://management.azure.com/";
    example = "https://management.azure.com/";
    type = types.str;
    description = ''
      The URI that identifies the resource for which the token is valid.
      If left empty, it defaults to the contents of the environment
      variable <envar>AZURE_ACTIVE_DIR_APP_IDENTIFIER_URI</envar>.
    '';
  };

  appId = mkOption {
    default = "";
    example = "aaaaaaaa-0000-aaaa-0000-aaaaaaaaaaaa";
    type = types.str;
    description = ''
      The ID of registrated application in Azure Active Directory.
      If left empty, it defaults to the contents of the environment
      variable <envar>AZURE_ACTIVE_DIR_APP_ID</envar>.
    '';
  };

  appKey = mkOption {
    default = "";
    type = types.str;
    description = ''
      The secret value of registrated application in Azure Active Directory.
      If left empty, it defaults to the contents of the environment
      variable <envar>AZURE_ACTIVE_DIR_APP_KEY</envar>.
    '';
  };

}
