{ lib, deployment, config, ... }:

let
  mkResourceOption = { name, pluralDisplayName, baseModules }: lib.mkOption {
    description = "The ${pluralDisplayName} in the network.";

    default = {};

    type = lib.types.attrsOf (lib.types.submodule (baseModules ++ deployment.resources.defaults.${name}));
  };

  # !!! Would be preferable to have a mkMap-style property instead
  # of having to have these default options here.
  mkDefaultOption = pluralDisplayName: lib.mkOption {
    description =
      "Extra configuration to apply to each of the ${pluralDisplayName} in the network";

    # !!! Should there be a type corresponding to module syntax?
    type = lib.types.listOf lib.types.unspecified;
  };

  resourceTypes = import ./resource-types.nix;

  pkgs = import <nixpkgs> {};
in {
  options = {
    resources = (lib.mapAttrs (name: value:
      mkResourceOption ({ inherit name; } // value)
    ) resourceTypes) // ({
      defaults = lib.mapAttrs (name: value:
        mkDefaultOption value.pluralDisplayName
      ) resourceTypes;
    });

    toplevel = lib.mkOption {
      description = "The top-level results of the module evaluation.";

      type = lib.types.attrsOf lib.types.unspecified;

      internal = true;
    };

    uuid = lib.mkOption {
      description = "The UUID of the network (set by nixops).";

      type = lib.types.str;

      internal = true;
    };

    description = lib.mkOption {
      description = "A human-readable description of the network.";

      default = "Unnamed NixOps network";

      type = lib.types.str;
    };

    enableRollback = lib.mkOption {
      description = "Whether or not to enable network-level rollback.";

      default = false;

      type = lib.types.bool;
    };
  };

  config = {
    __internal.args.deployment = config;

    resources.defaults = lib.mapAttrs (name: value:
      if name == "machines"
        then [ ({ name, ... }: {
          networking.hostName = lib.mkOverride 900 name;

          deployment.targetHost = lib.mkOverride 900 name;

          __internal.check = lib.mkOverride 900 deployment.__internal.check;

          __internal.args = {
            nodes = deployment.resources.machines;

            resources = deployment.resources;

            modules = [];

            inherit (value) baseModules;
          };
        }) ]
        else [ {
          # backwards compat
          __internal.check = lib.mkDefault false;

          __internal.args = {
            inherit pkgs;

            inherit (deployment) uuid resources;
          };
        } ]
    ) resourceTypes;

    toplevel = {
      info = {
        machines = lib.mapAttrs (n: v': let v = lib.scrubOptionValue v'; in {
          inherit (v.deployment) targetEnv targetPort targetHost encryptedLinksTo storeKeysOnMachine alwaysActivate owners keys;

          ec2 = lib.optionalAttrs (v.deployment.targetEnv == "ec2") v.deployment.ec2;

          hetzner = lib.optionalAttrs (v.deployment.targetEnv == "hetzner") v.deployment.hetzner;

          route53 = v.deployment.route53;

          virtualbox =
            let cfg = v.deployment.virtualbox; in
            lib.optionalAttrs (v.deployment.targetEnv == "virtualbox") (cfg // {
              disks = lib.mapAttrs (n: v: v //
                { baseImage = if lib.isDerivation v.baseImage then "drv" else toString v.baseImage; }
              ) cfg.disks;
            });
        }) deployment.resources.machines;

        network = { inherit (deployment) description enableRollback; };

        resources = removeAttrs deployment.resources [ "machines" "defaults" ];
      };

      nodes = lib.mapAttrs (n: v: { config = v; } ) deployment.resources.machines;

      machines = { names }:
        let machines = lib.filterAttrs (n: v: lib.elem n names) deployment.resources.machines; in
        pkgs.runCommand "nixops-machines" { preferLocalBuild = true; } ''
          mkdir -p $out
          ${toString (lib.attrValues (lib.mapAttrs (n: v: ''
            ln -s ${v.system.build.toplevel} $out/${n}
          '') machines))}
        '';
    };
  };
}
