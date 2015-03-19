{ config, pkgs, uuid, name, ... }:

with pkgs.lib;
with (import ./lib.nix pkgs);
{

  options = (import ./azure-credentials.nix pkgs "deployment") // {

    name = mkOption {
      example = "my-deployment";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Description of the Azure deployment. This is the <literal>Name</literal> tag of the deployment.";
    };

    label = mkOption {
      type = types.str;
      description = "Human-friendly label for the deployment up to 100 characters in length.";
    };

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
        Azure hosted service name or resource to deploy to.
      '';
    };

    ipAddress = mkOption {
      default = null;
      example = "resources.azureReservedIPAddresses.exampleIP";
      type = types.nullOr ( types.either types.str (resource "azure-reserved-ip-address") );
      description = ''
        Azure Static IP address resource or the name of
        an IP address not managed by NixOps to use as
        the public IP address of the deployment.
      '';
    };

    dummyDiskUrl = mkOption {
      type = types.str;
      description = ''
        URL of the BLOB of the root disk of the 'dummy' virtual machine.
        Due to Azure limitations, creating an empty deployment requires
        creating a placeholder machine which is immediately deallocated
        except for its root disk.
        The root disk is to be stored at the URL specified.
      '';
    };

  };

  config._type = "azure-deployment";

}
