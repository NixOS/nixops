{ system ? builtins.currentSystem
, networkExprs
, checkConfigurationOptions ? true
, uuid
, deploymentName
, args
, pluginNixExprs
}:

with import <nixpkgs/nixos/lib/testing.nix> { inherit system; };
with pkgs;
with lib;

rec {

  importedPluginNixExprs = map
    (expr: import expr)
    pluginNixExprs;
  pluginOptions = { imports = (foldl (a: e: a ++ e.options) [] importedPluginNixExprs); };
  pluginResources = map (e: e.resources) importedPluginNixExprs;
  pluginDeploymentConfigExporters = (foldl (a: e: a ++ (e.config_exporters { inherit optionalAttrs; })) [] importedPluginNixExprs);

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
            [ deploymentInfoModule ] ++
            [ { key = "nixops-stuff";
                # Make NixOps's deployment.* options available.
          imports = [ ./options.nix ./resource.nix pluginOptions ];
                # Provide a default hostname and deployment target equal
                # to the attribute name of the machine in the model.
                networking.hostName = mkOverride 900 machineName;
                deployment.targetHost = mkOverride 900 machineName;
                environment.checkConfigurationOptions = mkOverride 900 checkConfigurationOptions;
              }
            ];
          extraArgs = { inherit nodes resources uuid deploymentName; name = machineName; };
        };
      }
    ) (attrNames (removeAttrs network [ "network" "defaults" "resources" "require" "_file" ])));

  # Compute the definitions of the non-machine resources.
  resourcesByType = zipAttrs (network.resources or []);

  deploymentInfoModule = {
    deployment = {
      name = deploymentName;
      arguments = args;
      inherit uuid;
    };
  };

  evalResources = mainModule: _resources:
    mapAttrs (name: defs:
      (builtins.removeAttrs (fixMergeModules
        ([ mainModule deploymentInfoModule ./resource.nix ] ++ defs)
        { inherit pkgs uuid name resources; nodes = info.machines; }
      ).config) ["_module"]) _resources;

  resources = foldl
    (a: b: a // (b { inherit evalResources zipAttrs resourcesByType;}))
    {
      sshKeyPairs = evalResources ./ssh-keypair.nix (zipAttrs resourcesByType.sshKeyPairs or []);
      machines = mapAttrs (n: v: v.config) nodes;
    }
    pluginResources;

  # check if there are duplicate elements in a sorted list
  noDups = l:
    if length l > 1
    then
      if (head l) == (head (tail l))
      then throw "found resources with duplicate names: ${head l}"
      else noDups (tail l)
    else true;


  # Phase 1: evaluate only the deployment attributes.
  info =
    let
      network' = network;
      resources' = resources;
    in rec {

    machines =
      flip mapAttrs nodes (n: v': let v = scrubOptionValue v'; in
        foldl (a: b: a // b)
        { inherit (v.config.deployment) targetEnv targetPort targetHost encryptedLinksTo storeKeysOnMachine alwaysActivate owners keys hasFastConnection;
          nixosRelease = v.config.system.nixos.release or v.config.system.nixosRelease or (removeSuffix v.config.system.nixosVersionSuffix v.config.system.nixosVersion);
          publicIPv4 = v.config.networking.publicIPv4;
      }
      (map
        (f: f v.config)
        pluginDeploymentConfigExporters
      ));

    network = fold (as: bs: as // bs) {} (network'.network or []);

    resources =
    let
      resource_referenced = list: check: recurse:
          any id (map (value: (check value) ||
                              ((isAttrs value) && (!(value ? _type) || recurse)
                                               && (resource_referenced (attrValues value) check false)))
                      list);
      flatten_resources = resources: flatten ( map attrValues (attrValues resources) );

      resource_used = res_set: resource:
          resource_referenced
              ((flatten_resources res_set) ++ (attrValues azure_machines))
              (value: value == resource )
              true;

      resources_without_defaults = res_class: defaults: res_set:
        let
          missing = filter (res: !(resource_used (removeAttrs res_set [res_class])
                                                  res_set."${res_class}"."${res}"))
                           (attrNames defaults);
        in
        res_set // { "${res_class}" = ( removeAttrs res_set."${res_class}" missing ); };

    in (removeAttrs resources' [ "machines" ]);

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


  # Function needed to calculate the nixops arguments. This should work even when arguments
  # are not set yet, so we fake arguments to be able to evaluate the require attribute of
  # the nixops network expressions.

  dummyArgs = f: builtins.listToAttrs (map (a: lib.nameValuePair a false) (builtins.attrNames (builtins.functionArgs f)));

  getNixOpsExprs = l: lib.unique (lib.flatten (map getRequires l));

  getRequires = f:
    let
      nixopsExpr = import f;
      requires =
        if builtins.isFunction nixopsExpr then
          ((nixopsExpr (dummyArgs nixopsExpr)).require or [])
        else
          (nixopsExpr.require or []);
    in
      [ f ] ++ map getRequires requires;

  fileToArgs = f:
    let
      nixopsExpr = import f;
    in
      if builtins.isFunction nixopsExpr then
        map (a: { "${a}" = builtins.toString f; } ) (builtins.attrNames (builtins.functionArgs nixopsExpr))
      else [];

  getNixOpsArgs = fs: lib.zipAttrs (lib.unique (lib.concatMap fileToArgs (getNixOpsExprs fs)));

  nixopsArguments = getNixOpsArgs networkExprs;
}
