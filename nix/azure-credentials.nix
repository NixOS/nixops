pkgs: name:
with pkgs.lib;
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

  certificatePath = mkOption {
    default = "";
    example = "/path/to/client/certificate.pem";
    type = types.str;
    description = ''
      The path to Azure Management Certificate file. If left empty, it defaults to the
      contents of the environment variable <envar>AZURE_CERTIFICATE_PATH</envar>.
    '';
  };

}