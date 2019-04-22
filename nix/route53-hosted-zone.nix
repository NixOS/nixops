{ config, lib, uuid, name, ... }:

with lib;

{

  options = {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the recordset.";
    };

    accessKeyId = mkOption {
      type = types.str;
      default = "";
      description = ''
        The AWS Access Key ID.  If left empty, it defaults to the
        contents of the environment variables
        <envar>EC2_ACCESS_KEY</envar> or
        <envar>AWS_ACCESS_KEY_ID</envar> (in that order).  The
        corresponding Secret Access Key is not specified in the
        deployment model, but looked up in the file
        <filename>~/.ec2-keys</filename>, which should specify, on
        each line, an Access Key ID followed by the corresponding
        Secret Access Key. If the lookup was unsuccessful it is continued
        in the standard AWS tools <filename>~/.aws/credentials</filename> file.
        If it does not appear in these files, the
        environment variables
        <envar>EC2_SECRET_KEY</envar> or
        <envar>AWS_SECRET_ACCESS_KEY</envar> are used.
      '';
    };

    comment = mkOption {
      default = "";
      type = types.str;
      description = ''
        Comments that you want to include about the hosted zone.
      '';
    };

    privateZone = mkOption {
      default = false;
      type = types.bool;
      description = ''
        Whether this is a private hosted zone.
      '';
    };

    associatedVPCs = mkOption {
      type = with types; listOf (submodule {
        options = {
          vpcId = mkOption {
            type = str;
            description = "The ID of an Amazon VPC.";
          };
          region = mkOption {
            type = str;
            description = "The region in which you created an Amazon VPC.";
          };
        };
      });
      default = [];
      description = "VPCs";
    };

    delegationSet = mkOption {
      default = [];
      internal = true;
      type = types.listOf types.str;
      description = ''
        List of nameserves in the delegation set after creation. Set by nixops.
      '';
    };

  };

  config = {
    _type = "route53-hosted-zone";
  };
}
