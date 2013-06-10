{ config, lib, ... }:

let
  networkExprs = config.oldStyleNetworkExpressions;

  inherit (lib) mkOption zipAttrs types mapAttrs fold catAttrs hasAttr
    getAttr listToAttrs applyIfFunction flip concatLists;

  inherit (types) listOf path;

  call = flip applyIfFunction config.deployment.arguments;

  networks =
    let
      getNetworkFromExpr = networkExpr: call (import networkExpr);

      exprToKey = key: { inherit key; };

      networkExprClosure = builtins.genericClosure {
        startSet = map exprToKey networkExprs;

        operator = { key }: map exprToKey ((getNetworkFromExpr key).require or []);
      };
    in map ({ key }: getNetworkFromExpr key // { inherit key; }) networkExprClosure;

  defaults = concatLists (zipAttrs networks).defaults or [];

  machines = zipAttrs (map (network:
    mapAttrs (name: value: {
      key = network.key or "<unknown-old-style-network>";

      inherit value;
    }) (removeAttrs network [ "network" "defaults" "resources" "require" "key" ])
  ) networks);

in {
  options = {
    oldStyleNetworkExpressions = mkOption {
      description = "Old-style network expressions to include in the network";

      type = listOf path;

      default = [];
    };

    resources.machines.options = {
      imports = defaults;

      options = {};
    };
  };

  config = {
    network = fold (as: bs: as // bs) {} (catAttrs "network" networks);

    resources = listToAttrs (map (name: {
      inherit name;
      value = mapAttrs (name: values: args: {
        key = "<inline-nonsense>";
        imports =
          let
            arguments = args // {
              nodes = config.resources.machines;

              resources = removeAttrs config.resources [ "machines" ];

              uuid = config.deployment.uuid;
            };
          in map ({ key, value}: { inherit key; } // (applyIfFunction value arguments)) values;

        config = {};

        options = {};
      }) (if name == "machines"
        then machines
        else zipAttrs (map (network:
          mapAttrs (name: value: {
            key = network.key or "<unknown-old-style-network>";

            inherit value;
          }) (if hasAttr name (network.resources or {}) then getAttr name network.resources else {})
        ) networks));
    }) [ "machines" "ec2KeyPairs" "s3Buckets" "sqsQueues" "iamRoles" ]);
  };
}
