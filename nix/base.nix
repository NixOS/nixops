{ lib, ... }:
let
  inherit (lib) mkOption mkOverride;

  inherit (lib.types) attrsOf optionSet string bool attrs;
in {
  options = {
    resources = {
      machines = mkOption {
        description = "The machines in the network";

        type = attrsOf optionSet;

        options = { name, ... }: {
          imports = [ ./options.nix ] ++ import <nixos/modules/module-list.nix>;

          config = {
            networking.hostName = mkOverride 900 name;
            deployment.targetHost = mkOverride 900 name;
          };
        };
      };

      ec2KeyPairs = mkOption {
        description = "The EC2 key pairs in the network";

        type = attrsOf optionSet;

        options.imports = ./ec2-keypair.nix;
      };

      s3Buckets = mkOption {
        description = "The S3 buckets in the network";

        type = attrsOf optionSet;

        options.imports = ./s3-bucket.nix;
      };

      iamRoles = mkOption {
        description = "The IAM roles in the network";

        type = attrsOf optionSet;

        options.imports = ./iam-role.nix;
      };
    };

    network = {
      description = mkOption {
        description = "The description of the network";

        default = "Unnamed NixOps network";

        type = string;
      };

      enableRollback = mkOption {
        description = "Whether to enable rollback for the network";

        default = false;

        type = bool;
      };

    };

    deployment = {
      arguments = mkOption {
        description = "The deployment arguments";

        type = attrs;

        default = {};

        internal = true;
      };

      uuid = mkOption {
        description = "The deployment uuid";

        type = string;

        default = "";

        internal = true;
      };
    };
  };
}
