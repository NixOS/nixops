{ config, options, lib, system, ... }:
let
  inherit (lib) mkOption types;
  #TODO: remove after merging https://github.com/NixOS/nixpkgs/pull/163617
  deferredModule = with lib; mkOptionType {
    name = "deferredModule";
    description = "module";
    check = t: isAttrs t || isFunction t || builtins.isPath t;
    merge = loc: defs: map (def: lib.setDefaultModuleLocation "${showOption loc} from ${def.file}" def.value) defs;
  };
  # inherit (types) deferredModule;
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
          inherit (config) nodes resources;
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
          lib.warn "Please use nodes.${n} option instead of assigning machines to the config's top level"
            { inherit imports; })
        nodes);
    _module.freeformType = types.attrsOf deferredModule;
  };
}
