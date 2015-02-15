# Configuration specific to the Azure backend.

{ config, pkgs, name, uuid, resources, ... }:

with pkgs.lib;
with (import ./lib.nix pkgs);
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

      ipAddress = mkOption {
        default = null;
        example = "resources.azureReservedIPAddresses.exampleIP";
        type = types.nullOr ( types.either types.str (resource "azure-reserved-ip-address") );
        description = ''
          Azure Static IP address resource to bind to or the name of
          an IP address not managed by NixOps.
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

      slot = mkOption {
        default = "staging";
        example = "production";
        type = types.str;
        description = "Deployment slot: staging or production.";
      };

      hostedService = mkOption {
        default = null;
        example = "resources.azureHostedServices.myservice";
        type = types.either types.str (resource "azure-hosted-service");
        description = ''
          Azure hosted service name or resource to deploy the machine to.
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

    };

  };

  ###### implementation

  config = mkIf (config.deployment.targetEnv == "azure") {
    nixpkgs.system = mkOverride 900 "x86_64-linux";
  };
}
