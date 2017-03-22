{ config, pkgs, lib, utils, ... }:

with utils;
with lib;
with import ./lib.nix lib;

let
  cfg = config.deployment.vultr;
in
{
  ###### interface
  options = {

    deployment.vultr.label = mkOption {
      default = "";
      example = "myserver.example.com";
      type = types.str;
      description = ''
        The name of the server.
      '';
    };

    deployment.vultr.dcid = mkOption {
      default = "";
      example = "1";
      type = types.str;
      description = ''
        The region. See region_list API for list of regions available
      '';
    };

    deployment.vultr.vpsplanid = mkOption {
      example = "201";
      type = types.str;
      description = ''
        The VPSPLANID. Make sure the region you chose supports the plan ID.
        This determines the resources and cost of the instance.
      '';
    };
    deployment.vultr.snapshotid = mkOption {
      example = "9e758d1a379eb";
      type = types.str;
      description = ''
        The snapshotid. This needs created following this tutorial:
        https://www.vultr.com/docs/install-nixos-on-vultr
      '';
    };
  };

  config = mkIf (config.deployment.targetEnv == "vultr") {
    nixpkgs.system = mkOverride 900 "x86_64-linux";
    services.openssh.enable = true;
  };
}
