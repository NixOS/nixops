# Configuration specific to the Azure backend.

{ config, pkgs, name, uuid, resources, ... }:

with pkgs.lib;
with (import ./lib.nix pkgs);
let

  endpointOptions = { config, ... }: {

    options = {

      port = mkOption {
        example = 22;
        type = types.int;
        description = ''
          External port number bound to the public IP of the deployment.
        '';
      };

      localPort = mkOption {
        example = 22;
        type = types.int;
        description = ''
          Local port number bound to the the VM network interface.
        '';
      };

      setName = mkOption {
        default = null;
        example = 22;
        type = types.nullOr types.str;
        description = ''
          Name of the load-balanced endpoint set.
        '';
      };

      directServerReturn = mkOption {
        default = false;
        example = true;
        type = types.bool;
        description = ''
          Enable direct server return.
        '';
      };

    };

    config = {};

  };

in
{
  ###### interface

  options = {

    deployment.azure = (import ./azure-credentials.nix pkgs "instance") // {

      machineName = mkOption {
        default = "n-${shorten_uuid uuid}-${name}";
        example = "custom-machine-name";
        type = types.str;
        description = "The Azure machine <literal>Name</literal>.";
      };


      roleSize = mkOption {
        default = "Small";
        example = "Large";
        type = types.str;
        description = ''
            The size of the virtual machine to allocate.
            Possible values are: ExtraSmall, Small, Medium, Large, ExtraLarge. 
        '';
      };

#      storage = mkOption {
#        default = null;
#        example = "resources.azureStorages.mystorage";
#        type = types.either types.str (resource "azure-storage");
#        description = ''
#          Azure storage service name or resource to use to manage the underlying disk BLOBs.
#        '';
#      };

      hostedService = mkOption {
        default = null;
        example = "resources.azureHostedServices.myservice";
        type = types.either types.str (resource "azure-hosted-service");
        description = ''
          Azure hosted service name or resource to deploy the machine to.
        '';
      };

      deployment = mkOption {
        default = null;
        example = "resources.azureDesployments.mydeployment";
        type = types.either types.str (resource "azure-deployment");
        description = ''
          Azure deployment name or resource to deploy the machine to.
        '';
      };

      rootDiskImage = mkOption {
        example = "nixos-bootstrap-30GB";
        type = types.str;
        description = ''
          Bootstrap image URL.
        '';
      };

      rootDiskUrl = mkOption {
        example = "http://mystorage.blob.core.windows.net/mycontainer/machine-root";
        type = types.str;
        description = ''
          URL of the BLOB of the root disk. Will be created if neccessary.
        '';
      };

      inputEndpoints.tcp = mkOption {
        default = { };
        example = { ssh = { port = 33; localPort = 22; }; };
        type = types.attrsOf types.optionSet;
        options = endpointOptions;
        description = ''
          TCP input endpoint options.
        '';
      };

      inputEndpoints.udp = mkOption {
        default = { };
        example = { dns = { port = 53; localPort = 640; }; };
        type = types.attrsOf types.optionSet;
        options = endpointOptions;
        description = ''
          UDP input endpoint options.
        '';
      };

      obtainIP = mkOption {
        default = false;
        example = true;
        type = types.bool;
        description = ''
          Whether to obtain a dedicated public IP for the instance.
        '';
      };

    };

  };

  ###### implementation

  config = mkIf (config.deployment.targetEnv == "azure") {
    nixpkgs.system = mkOverride 900 "x86_64-linux";
  };
}
