{ config, pkgs, lib, utils, ... }:

with utils;
with lib;
with import ./lib.nix lib;

let
  cfg = config.deployment.hetznerCloud;
in
{
  ###### interface
  options = {

    deployment.hetznerCloud.authToken = mkOption {
      default = "";
      example = "8b2f4e96af3997853bfd4cd8998958eab871d9614e35d63fab45a5ddf981c4da";
      type = types.str;
      description = ''
        The API auth token. We're checking the environment for
        <envar>HETZNER_CLOUD_AUTH_TOKEN</envar> first and if that is
        not set we try this auth token.
      '';
    };

    deployment.hetznerCloud.datacenter = mkOption {
      example = "fsn1-dc8";
      default = null;
      type = types.nullOr types.str;
      description = ''
        The datacenter.
      '';
    };

    deployment.hetznerCloud.location = mkOption {
      example = "fsn1";
      default = null;
      type = types.nullOr types.str;
      description = ''
        The location.
      '';
    };

    deployment.hetznerCloud.serverType = mkOption {
      example = "cx11";
      type = types.str;
      description = ''
        Name or id of server types.
      '';
    };
  };

  config = mkIf (config.deployment.targetEnv == "hetznerCloud") {
    nixpkgs.system = mkOverride 900 "x86_64-linux";
    services.openssh.enable = true;
  };
}
