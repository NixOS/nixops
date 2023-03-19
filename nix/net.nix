{ config, options, lib, system, ... }:
let
  inherit (lib) mkOption types mapAttrs warn;
  inherit (types) deferredModule;

  deploymentDefault = {
    imports = [ ./resource.nix ./default-deployment.nix ];
    inherit (config) deployment;
  };
in
{
  imports = [ ./default-deployment.nix ];
  options = {
    nixpkgs = lib.mkOption {
      type = types.path;
      description = "Path to the nixpkgs instance used to build the machines.";
      defaultText = lib.literalDocBook "The 'nixpkgs' input to either the provided flake or nixops' own.";
    };
    network = {
      enableRollback = lib.mkEnableOption "network wide rollback";
      description = mkOption {
        type = types.str;
        description = "A description of the entire network.";
        default = "";
      };
      nodesExtraArgs = mkOption {
        description = "Extra inputs to be passed to every node.";
        type = with types;attrsOf anything;
        default = { };
      };
      storage = mkOption {
        description = "Configuring how to store the network state.";
        default = { };
        type = with types; submodule {
          _module.freeformType = attrsOf anything;
        };
      };
      resourcesDefaults = mkOption {
        type = deferredModule;
        internal = true;
        default = { };
        description = ''
          Extra configurations to add to all resources.
        '';
      };
      lock = mkOption {
        # TBD
        type = types.raw;
        default = { };
      };
    };
    resources = mkOption {
      default = { };
      type = types.submoduleWith {
        specialArgs.defineResource = resName: resMod: {
          options.${resName} = mkOption {
            default = { };
            type = types.attrsOf (types.submoduleWith {
              specialArgs = {
                inherit (config) resources;
                inherit (config.deployment) uuid;
              };
              modules = [
                deploymentDefault
                config.network.resourcesDefaults
                resMod
                ({ name, ... }: {
                  _module.args.nodes = # inherit nodes, essentially
                    lib.mapAttrs
                      (nodeName: node:
                        lib.mapAttrs
                          (key: lib.warn "Resource ${name} accesses nodes.${nodeName}.${key}, which is deprecated. Use the equivalent option instead: nodes.${nodeName}.${{
                          nixosRelease = "config.system.nixos.release and make sure it is set properly";
                          publicIPv4 = "config.networking.publicIPv4";
                        }.${key} or "config.deployment.${key}"}.")
                          config.resources.machines.${nodeName}
                        // node)
                      config.resources.machines;
                })
              ];
            });
          };
        };
        modules = [
          deploymentDefault
          ({ defineResource, ... }: {
            imports = [
              (defineResource "sshKeyPairs" ./ssh-keypair.nix)
              (defineResource "commandOutput" ./command-output.nix)
              (defineResource "machines" ./options.nix)
            ];
            # Compute the definitions of the machines.
            options.machines = mkOption {
              description = "The NixOS configurations for the nodes in the network.";
              # on 1st eval nodes is not read and on 2nd lib is taken from config.nixpkgs
              type = types.attrsOf (lib.nixosSystem or (import /${config.nixpkgs}/nixos/lib/eval-config.nix) {
                inherit system lib;
                specialArgs = config.network.nodesExtraArgs;
                modules = [ config.defaults { _module.check = true; } ];
              }).type;
            };
            config._module.check = false;
          })
        ];
      };
    };
    defaults = mkOption {
      type = deferredModule;
      default = { };
      description = ''
        Extra NixOS options to add to all nodes.
      '';
    };
  };
  config = {
    resources.machines =
      let
        nodes = removeAttrs config (builtins.attrNames options);
      in
      lib.mkIf ({ } != nodes) (lib.mapAttrs
        (name: node: {
          imports = [ node ];
          warnings = [ "Please use nodes.${name} option instead of assigning machines to the config's top level" ];
        })
        nodes);

    # Provides compatibility for old style node definitions outside in the root,
    # outside the `nodes` option.
    # TODO: interpreting arbitrary _mistaken_ configs as machines leads to
    #       obscure errors, so we should consider removing this backcompat
    #       solution, or perhaps eagerly throw an appropriate error as soon as
    #       we encounter an unknown key. The warning may not be encountered.
    _module.freeformType = types.attrsOf deferredModule;
  };
}
