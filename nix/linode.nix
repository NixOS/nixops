{ config, pkgs, lib, utils, ... }:

with lib;

let
  cfg = config.deployment.linode;
in
{
  ###### interface
  options = {
    deployment.linode.personalAPIKey = mkOption {
      default = "";
      example = "2f99e7484232eh7dg8780ak41d371a945d4092150be5d36aee19d352df31a45f";
      type = types.str;
      description = ''
        Your personal API key. Create this from https://cloud.linode.com/profile/integrations/tokens
        Needs 'Delete' privilege for Linodes.
        We check for this value in <envar>LINODE_PERSONAL_API_KEY</envar> before looking here.
      '';
    };

    deployment.linode.region = mkOption {
      default = "eu-west-1a";
      example = "eu-west-1a";
      type = types.str;
      description = ''
        The id of the region to deploy the VM into.

        See https://api.linode.com/v4/regions for available regions (use the id field).

        Alternatively, run `curl https://api.linode.com/v4/regions | jq ".regions[].id"`
      '';
    };

    deployment.linode.type = mkOption {
      default = "g5-nanode-1";
      example = "g5-nanode-1";
      type = types.str;
      description = ''
        The id of the type of VM to deploy. This determines the amount
        of storage, memory, virtual CPUs, price, and network
        bandwidth.

        See https://api.linode.com/v4/linode/types for available types.

        Alternatively, run `curl https://api.linode.com/v4/types | jq ".types[].id"`
      '';
    };
  };

  config = mkIf (config.deployment.targetEnv == "linode") {
    nixpkgs.system = mkOverride 900 "x86_64-linux";
    services.openssh.enable = true; # We need an SSH server in order to deploy our configuration.

    ## TODO: do we need to muck around with Grub?
  };
}
