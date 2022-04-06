{ config, options, lib, system, ... }:
let
  inherit (lib) mkOption types mapAttrs warn;
  #TODO: remove after merging https://github.com/NixOS/nixpkgs/pull/163617
  deferredModule = with lib; mkOptionType {
    name = "deferredModule";
    description = "module";
    check = t: isAttrs t || isFunction t || builtins.isPath t;
    merge = loc: defs: map (def: lib.setDefaultModuleLocation "${showOption loc} from ${def.file}" def.value) defs;
  };
  # inherit (types) deferredModule;

  nodesConfigCompat = k: n:
    n // {
      config =
        warn
          "The module parameter `nodes.${lib.strings.escapeNixIdentifier k}.config' has been renamed to `nodes.${lib.strings.escapeNixIdentifier k}'"
          n;
      options = throw "nodes.<name>.options is not available anymore. You can access options information by writing a node-level module that extracts the options information and assigns it to a new option of your choosing.";
    };
in
{
  options = {
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
    };
    # Compute the definitions of the machines.
    nodes = mkOption {
      description = "The NixOS configurations for the nodes in the network.";
      type = types.attrsOf (import "${config.nixpkgs}/nixos/lib/eval-config.nix" {
        inherit system lib;
        specialArgs = {
          inherit (config) resources;
          nodes = mapAttrs nodesConfigCompat config.nodes;
        } // config.network.nodesExtraArgs;
        modules =
          config.defaults ++
          # Make NixOps's deployment.* options available.
          [
            ./options.nix
            ./resource.nix
            ({ name, ... }: rec{
              _file = ./net.nix;
              key = _file;
              # Provide a default hostname and deployment target equal
              # to the attribute name of the machine in the model.
              networking.hostName = lib.mkOverride 900 name;
              deployment.targetHost = lib.mkOverride 900 name;
            })
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
        (n: imports: #TODO: actual warning/assert module impl.
          lib.warn "Please write to `nodes.${n}' instead of a top-level `${n}' config."
            { inherit imports; })
        nodes);
    _module.freeformType = types.attrsOf deferredModule;
  };
}
