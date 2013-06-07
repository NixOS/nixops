{ lib, config, ... }:
let
  inherit (lib) mkOption mkOverride types;

  inherit (types) attrsOf optionSet string bool attrs uniq;

  baseModules = [ ./options.nix ] ++ import <nixos/modules/module-list.nix>;
in {
  options = {
    resources = {
      machines = mkOption {
        default = {};

        description = "The machines in the network";

        type = attrsOf optionSet;

        extraArgs = {
          inherit baseModules;

          modules = []; #!!! What makes sense here?

          modulesPath = <nixos/modules>;
        };

        options = { name, ... }: {
          imports = baseModules;

          config = {
            networking.hostName = mkOverride 900 name;

            deployment.targetHost = mkOverride 900 name;
          };
        };
      };

      ec2KeyPairs = mkOption {
        default = {};

        description = "The EC2 key pairs in the network";

        type = attrsOf optionSet;

        extraArgs = { inherit lib; uuid = config.deployment.uuid; };

        options.imports = [ ./ec2-keypair.nix ];

        options.options = {};
      };

      s3Buckets = mkOption {
        default = {};

        description = "The S3 buckets in the network";

        type = attrsOf optionSet;

        extraArgs = { inherit lib; uuid = config.deployment.uuid; };

        options.imports = [ ./s3-bucket.nix ];

        options.options = {};
      };

      iamRoles = mkOption {
        default = {};

        description = "The IAM roles in the network";

        type = attrsOf optionSet;

        extraArgs = { inherit lib; uuid = config.deployment.uuid; };

        options.imports = [ ./iam-role.nix ];

        options.options = {};
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

        type = uniq attrs;

        internal = true;
      };

      uuid = mkOption {
        description = "The deployment uuid";

        type = uniq string;

        internal = true;
      };

      checkConfigurationOptions = mkOption {
        description = "Whether to check the validity of the entire configuration";

        type = uniq bool;

        internal = true;
      };
    };
  };
}
