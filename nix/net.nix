{ config, options, lib, system, ... }:
let
  inherit (lib) mkOption types mapAttrs warn;
  inherit (types) deferredModule;

  nodesConfigCompat = k: n:
    n // {
      config =
        warn
          "The module parameter `nodes.${lib.strings.escapeNixIdentifier k}.config' has been renamed to `nodes.${lib.strings.escapeNixIdentifier k}'"
          n;
      options = throw "nodes.<name>.options is not available anymore. You can access options information by writing a node-level module that extracts the options information and assigns it to a new option of your choosing.";
    };

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
        default = {};
      };
    };
    resources = mkOption {
      default = { };
      type = types.submoduleWith {
        specialArgs.defineResource = resName: resMod: {
          options.${resName} = mkOption {
            default = { };
            type = types.attrsOf (types.submodule ({ name, ... }: {
              imports=[
                deploymentDefault
                config.network.resourcesDefaults
                resMod
              ];
              _module.args = {
                inherit (config) resources;
                nodes = # inherit nodes, essentially
                  lib.mapAttrs
                    (nodeName: node:
                      lib.mapAttrs
                        (key: lib.warn "Resource ${name} accesses nodes.${nodeName}.${key}, which is deprecated. Use the equivalent option instead: nodes.${nodeName}.${{
                          nixosRelease = "config.system.nixos.release and make sure it is set properly";
                          publicIPv4 = "config.networking.publicIPv4";
                        }.${key} or "config.deployment.${key}"}.")
                        config.nodes.${nodeName}
                      // node)
                    config.nodes;
              };
            }));
          };
        };
        modules = [
          deploymentDefault
          ({ defineResource, ... }: {
            imports = [
              (defineResource "sshKeyPairs" ./ssh-keypair.nix)
              (defineResource "commandOutput" ./command-output.nix)
            ];
            options.machines = lib.mkOption {
              description = ''
                An alias for the `nodes`.
              '';
              readOnly = true;
              type = types.raw;
            };
            config = {
              machines = config.nodes;
              _module.check = false;
            };
          })
        ];
      };
    };
    # Compute the definitions of the machines.
    nodes = mkOption {
      description = "The NixOS configurations for the nodes in the network.";
      default = { };
      # on 1st eval nodes is not read and on 2nd lib is taken from config.nixpkgs
      type = types.attrsOf (lib.nixosSystem or (import /${config.nixpkgs}/nixos/lib/eval-config.nix) {
        inherit system lib;
        specialArgs = {
          inherit (config) resources;
          nodes = mapAttrs nodesConfigCompat config.nodes;
        } // config.network.nodesExtraArgs;
        modules = [
          config.defaults
          # Make NixOps's deployment.* options available.
          ./options.nix
          deploymentDefault
        ];
      }).type;
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
    nodes =
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
