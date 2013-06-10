{ system ? builtins.currentSystem
, networkExprs
, checkConfigurationOptions ? true
, uuid
, args
}:

let
  pkgs = import <nixpkgs> { inherit system; };

  inherit (pkgs) lib runCommand;

  inherit (lib) fixMergeModules scrubOptionValue mkOption mapAttrs mapAttrsToList filterAttrs elem optionalAttrs isDerivation attrValues getAttr listToAttrs;

  makeSystemModule = machines: fixMergeModules [ {
    key = ./eval-machine-info.nix;

    imports = [ ./old-style-networks.nix ]; # Required here because this will eventually only be used for backwards-compat

    options = {
      resources.machines = mkOption {
        extraArgs = rec {
          pkgs = import <nixpkgs> { config = {}; inherit system; };

          pkgs_i686 = pkgs.pkgsi686Linux;

          utils = import <nixos/lib/utils.nix> pkgs;
        };

        individualExtraArgs = mapAttrs (name: config: rec {
          pkgs = import <nixpkgs> { inherit (config.nixpkgs) system config; };

          pkgs_i686 = pkgs.pkgsi686Linux;

          utils = import <nixos/lib/utils.nix> pkgs;
        } ) machines;
      };
    };

    config = {
      oldStyleNetworkExpressions = networkExprs;

      deployment = {
        arguments = args;

        inherit uuid;
      };
    };
  } ./base.nix ] { inherit lib; };

  stage1SystemModule = makeSystemModule {};

  eval = makeSystemModule stage1SystemModule.config.resources.machines;

  config = assert checkConfigurationOptions -> lib.checkModule "" eval; eval.config;
in rec {
  nodes = listToAttrs (map (name: {
    inherit name;

    value = {
      config = getAttr name config.resources.machines;

      options = getAttr name eval.options.resources.machines;
    };
  }) (builtins.attrNames config.resources.machines));

  resources = removeAttrs config.resources [ "machines" ];

  info = {
    machines = mapAttrs (n: v': let v = scrubOptionValue v'; in
      { inherit (v.config.deployment) targetEnv targetHost encryptedLinksTo storeKeysOnMachine owners keys;
        adhoc = optionalAttrs (v.config.deployment.targetEnv == "adhoc") v.config.deployment.adhoc;
        ec2 = optionalAttrs (v.config.deployment.targetEnv == "ec2") v.config.deployment.ec2;
        route53 = v.config.deployment.route53;
        virtualbox =
          let cfg = v.config.deployment.virtualbox; in
          optionalAttrs (v.config.deployment.targetEnv == "virtualbox") (cfg
            // { disks = mapAttrs (n: v: v //
              { baseImage = if isDerivation v.baseImage then "drv" else toString v.baseImage; }) cfg.disks; });
      }
    ) nodes;

    network = config.network;

    inherit resources;
  };

  machines = { names }:
    let nodes' = filterAttrs (n: v: elem n names) nodes; in
    runCommand "nixops-machines"
      { preferLocalBuild = true; }
      ''
        mkdir -p $out
        ${toString (attrValues (mapAttrs (n: v: ''
          ln -s ${v.config.system.build.toplevel} $out/${n}
        '') nodes'))}
      '';
}
