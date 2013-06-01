{ config, pkgs, ... }:

let
  networkExprs = config.oldStyleNetworkExpressions;

  inherit (pkgs.lib) mkOption zipAttrs mkIf types mapAttrs;

  inherit (types) listOf path;

  networks =
    let
      getNetworkFromExpr = networkExpr: call (import networkExpr);

      exprToKey = key: { inherit key; };

      networkExprClosure = builtins.genericClosure {
        startSet = map exprToKey networkExprs;

        operator = { key }: map exprToKey ((getNetworkFromExpr key).require or []);
      };
    in map ({ key }: getNetworkFromExpr key // { inherit key; }) networkExprClosure;

  call = x: if builtins.isFunction x then x config.deployment.arguments else x;

  defaults = (zipAttrs networks).defaults;
in {
  options = {
    oldStyleNetworkExpressions = mkOption {
      description = "Old-style network expressions to include in the network";

      type = listOf path;

      default = [];
    };

    resources.machines.options.imports = defaults;
  };

  imports = map (network: {
    inherit (network) key;

    config = {
      network = mkIf (network ? network) network.network;

      resources = mapAttrs (name: value: builtins.listToAttrs [ {
        inherit name;

        value = mapAttrs (name: value: builtins.listToAttrs [ {
          inherit name;

          value = args:
            let
              arguments = args // {
                nodes = config.resources.machines;

                resources = removeAttrs config.resources [ "machines" ];

                uuid = config.deployment.uuid;

                inherit name;
              };
            in if builtins.isFunction value then value arguments else value;
        } ]) value;
      } ]) (network.resources // {
        machines = removeAttrs network [ "network" "defaults" "resources" "require" ];
      });
    };
  }) networks;
}
