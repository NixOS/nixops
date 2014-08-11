{ system ? builtins.currentSystem
, networkExprs
, checkConfigurationOptions ? true
, uuid
, args
}:

with import <nixpkgs/nixos/lib/testing.nix> { inherit system; };
with pkgs;
with lib;


rec {

  networks =
    let
      getNetworkFromExpr = networkExpr:
        (call (import networkExpr)) // { _file = networkExpr; };

      exprToKey = key: { key = toString key; };

      networkExprClosure = builtins.genericClosure {
        startSet = map exprToKey networkExprs;
        operator = { key }: map exprToKey ((getNetworkFromExpr key).require or []);
      };
    in map ({ key }: getNetworkFromExpr key) networkExprClosure;

  call = x: if builtins.isFunction x then x args else x;

  network = zipAttrs networks;

  defaults = network.defaults or [];

  # Compute the definitions of the machines.
  nodes =
    listToAttrs (map (machineName:
      let
        # Get the configuration of this machine from each network
        # expression, attaching _file attributes so the NixOS module
        # system can give sensible error messages.
        modules =
          concatMap (n: optional (hasAttr machineName n)
            { imports = [(getAttr machineName n)]; inherit (n) _file; })
          networks;
      in
      { name = machineName;
        value = import <nixpkgs/nixos/lib/eval-config.nix> {
          modules =
            modules ++
            defaults ++
            [ { key = "nixops-stuff";
                # Make NixOps's deployment.* options available.
                require = [ ./options.nix ];
                # Provide a default hostname and deployment target equal
                # to the attribute name of the machine in the model.
                networking.hostName = mkOverride 900 machineName;
                deployment.targetHost = mkOverride 900 machineName;
                environment.checkConfigurationOptions = mkOverride 900 checkConfigurationOptions;
              }
            ];
          extraArgs = { inherit nodes resources; };
        };
      }
    ) (attrNames (removeAttrs network [ "network" "defaults" "resources" "require" "_file" ])));

  # Compute the definitions of the non-machine resources.
  resourcesByType = zipAttrs (network.resources or []);

  evalResources = mainModule: _resources:
    mapAttrs (name: defs:
      (fixMergeModules
        ([ mainModule ./resource.nix ] ++ defs)
        { inherit pkgs uuid name resources; }
      ).config) _resources;

  resources.sqsQueues = evalResources ./sqs-queue.nix (zipAttrs resourcesByType.sqsQueues or []);
  resources.ec2KeyPairs = evalResources ./ec2-keypair.nix (zipAttrs resourcesByType.ec2KeyPairs or []);
  resources.sshKeyPairs = evalResources ./ssh-keypair.nix (zipAttrs resourcesByType.sshKeyPairs or []);
  resources.s3Buckets = evalResources ./s3-bucket.nix (zipAttrs resourcesByType.s3Buckets or []);
  resources.iamRoles = evalResources ./iam-role.nix (zipAttrs resourcesByType.iamRoles or []);
  resources.ec2SecurityGroups = evalResources ./ec2-security-group.nix (zipAttrs resourcesByType.ec2SecurityGroups or []);
  resources.ec2PlacementGroups = evalResources ./ec2-placement-group.nix (zipAttrs resourcesByType.ec2PlacementGroups or []);
  resources.ebsVolumes = evalResources ./ebs-volume.nix (zipAttrs resourcesByType.ebsVolumes or []);
  resources.elasticIPs = evalResources ./elastic-ip.nix (zipAttrs resourcesByType.elasticIPs or []);

  # Phase 1: evaluate only the deployment attributes.
  info = {

    machines =
      flip mapAttrs nodes (n: v': let v = scrubOptionValue v'; in
        { inherit (v.config.deployment) targetEnv targetPort targetHost encryptedLinksTo storeKeysOnMachine alwaysActivate owners keys;
          #adhoc = optionalAttrs (v.config.deployment.targetEnv == "adhoc") v.config.deployment.adhoc;
          ec2 = optionalAttrs (v.config.deployment.targetEnv == "ec2") v.config.deployment.ec2;
          hetzner = optionalAttrs (v.config.deployment.targetEnv == "hetzner") v.config.deployment.hetzner;
          container = optionalAttrs (v.config.deployment.targetEnv == "container") v.config.deployment.container;
          route53 = v.config.deployment.route53;
          virtualbox =
            let cfg = v.config.deployment.virtualbox; in
            optionalAttrs (v.config.deployment.targetEnv == "virtualbox") (cfg
              // { disks = mapAttrs (n: v: v //
                { baseImage = if isDerivation v.baseImage then "drv" else toString v.baseImage; }) cfg.disks; });
        }
      );

    network = fold (as: bs: as // bs) {} (network.network or []);

    inherit resources;

  };

  # Phase 2: build complete machine configurations.
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
