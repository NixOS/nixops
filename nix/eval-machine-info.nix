{ system ? builtins.currentSystem
, networkExprs
, flakeUri ? null
, checkConfigurationOptions ? true
, uuid
, deploymentName
, args
, pluginNixExprs
}:

let
  call = x: if builtins.isFunction x then x args else x;

  # Copied from nixpkgs to avoid <nixpkgs> import
  optional = cond: elem: if cond then [elem] else [];

  zipAttrs = set: builtins.listToAttrs (
    map (name: { inherit name; value = builtins.catAttrs name set; }) (builtins.concatMap builtins.attrNames set));

  networks =
    let
      getNetworkFromExpr = networkExpr:
        (call (import networkExpr)) // { _file = networkExpr; };

      exprToKey = key: { key = toString key; };

      networkExprClosure = builtins.genericClosure {
        startSet = map exprToKey networkExprs;
        operator = { key }: map exprToKey ((getNetworkFromExpr key).require or []);
      };
    in
      map ({ key }: getNetworkFromExpr key) networkExprClosure
      ++ optional (flakeUri != null)
        ((call (builtins.getFlake flakeUri).outputs.nixopsConfigurations.default) // { _file = "<${flakeUri}>"; });

  network = zipAttrs networks;

  evalConfig =
    if flakeUri != null
    then
      if network ? nixpkgs
      then (builtins.head (network.nixpkgs)).lib.nixosSystem
      else throw "NixOps network must have a 'nixpkgs' attribute"
    else import (pkgs.path + "/nixos/lib/eval-config.nix");

  pkgs = if flakeUri != null
    then
      if network ? nixpkgs
      then (builtins.head network.nixpkgs).legacyPackages.${system}
      else throw "NixOps network must have a 'nixpkgs' attribute"
    else (builtins.head (network.network)).nixpkgs or (import <nixpkgs> { inherit system; });

  inherit (pkgs) lib;

  # Expose path to imported nixpkgs (currently only used to find version suffix)
  nixpkgs = builtins.unsafeDiscardStringContext pkgs.path;

in rec {

  inherit networks network;
  inherit nixpkgs;

  importedPluginNixExprs = map
    (expr: import expr)
    pluginNixExprs;
  pluginOptions = { imports = (lib.foldl (a: e: a ++ e.options) [] importedPluginNixExprs); };
  pluginResources = map (e: e.resources) importedPluginNixExprs;
  pluginDeploymentConfigExporters = (lib.foldl (a: e: a ++ (e.config_exporters {
    inherit pkgs;
    inherit (lib) optionalAttrs;
  })) [] importedPluginNixExprs);

  defaults = network.defaults or [];

  # Compute the definitions of the machines.
  nodes =
    lib.listToAttrs (map (machineName:
      let
        # Get the configuration of this machine from each network
        # expression, attaching _file attributes so the NixOS module
        # system can give sensible error messages.
        modules =
          lib.concatMap (n: lib.optional (lib.hasAttr machineName n)
            { imports = [(lib.getAttr machineName n)]; inherit (n) _file; })
          networks;
      in
      { name = machineName;
        value = evalConfig {
          inherit pkgs;
          modules =
            modules ++
            defaults ++
            [ deploymentInfoModule ] ++
            [ { key = "nixops-stuff";
                # Make NixOps's deployment.* options available.
                imports = [ ./options.nix ./resource.nix pluginOptions ];
                # Provide a default hostname and deployment target equal
                # to the attribute name of the machine in the model.
                networking.hostName = lib.mkOverride 900 machineName;
                deployment.targetHost = lib.mkOverride 900 machineName;
                environment.checkConfigurationOptions = lib.mkOverride 900 checkConfigurationOptions;
              }
            ];
          extraArgs = { inherit nodes resources uuid deploymentName; name = machineName; };
        };
      }
    ) (lib.attrNames (removeAttrs network [ "network" "defaults" "resources" "require" "nixpkgs" "_file" ])));

  # Compute the definitions of the non-machine resources.
  resourcesByType = lib.zipAttrs (network.resources or []);

  deploymentInfoModule = {
    deployment = {
      name = deploymentName;
      arguments = args;
      inherit uuid;
    };
  };

  evalResources = mainModule: _resources:
    lib.mapAttrs (name: defs:
      (builtins.removeAttrs (lib.fixMergeModules
        ([ mainModule deploymentInfoModule ./resource.nix ] ++ defs)
        { inherit pkgs uuid name resources; nodes = info.machines; }
      ).config) ["_module"]) _resources;

  resources = lib.foldl
    (a: b: a // (b {
      inherit evalResources resourcesByType;
      inherit (lib) zipAttrs;
    }))
    {
      sshKeyPairs = evalResources ./ssh-keypair.nix (lib.zipAttrs resourcesByType.sshKeyPairs or []);
      commandOutput = evalResources ./command-output.nix (lib.zipAttrs resourcesByType.commandOutput or []);
      machines = lib.mapAttrs (n: v: v.config) nodes;
    }
    pluginResources;

  # check if there are duplicate elements in a sorted list
  noDups = l:
    if lib.length l > 1
    then
      if (lib.head l) == (lib.head (lib.tail l))
      then throw "found resources with duplicate names: ${lib.head l}"
      else noDups (lib.tail l)
    else true;

  # Phase 1: evaluate only the deployment attributes.
  info =
    let
      network' = network;
      resources' = resources;
    in rec {

    machines =
      lib.flip lib.mapAttrs nodes (n: v': let v = lib.scrubOptionValue v'; in
      lib.foldr (a: b: a // b)
        {
          inherit (v.config.deployment)
            targetEnv
            targetPort
            targetHost
            targetUser
            sshOptions
            privilegeEscalationCommand
            alwaysActivate
            owners
            keys
            hasFastConnection
            provisionSSHKey
            ;
          nixosRelease = v.config.system.nixos.release or v.config.system.nixosRelease or (lib.removeSuffix v.config.system.nixosVersionSuffix v.config.system.nixosVersion);
          publicIPv4 = v.config.networking.publicIPv4;
        }
      (map
        (f: f v.config)
        pluginDeploymentConfigExporters
      ));

    network =
      builtins.removeAttrs
      (lib.fold (as: bs: as // bs) {} (network'.network or []))
      [ "nixpkgs" ]  # Not serialisable
      ;

    resources =
    let
      resource_referenced = list: check: recurse:
          lib.any lib.id (map (value: (check value) ||
                              ((lib.isAttrs value) && (!(value ? _type) || recurse)
                                               && (resource_referenced (lib.attrValues value) check false)))
                      list);

      flatten_resources = resources: lib.flatten ( map lib.attrValues (lib.attrValues resources) );

      resource_used = res_set: resource:
          resource_referenced
              (flatten_resources res_set)
              (value: value == resource )
              true;

      resources_without_defaults = res_class: defaults: res_set:
        let
          missing = lib.filter (res: !(resource_used (removeAttrs res_set [res_class])
                                                  res_set."${res_class}"."${res}"))
                           (lib.attrNames defaults);
        in
        res_set // { "${res_class}" = ( removeAttrs res_set."${res_class}" missing ); };

    in (removeAttrs resources' [ "machines" ]);

  };

  # Phase 2: build complete machine configurations.
  machines = { names }:
    let nodes' = lib.filterAttrs (n: v: lib.elem n names) nodes; in
    pkgs.runCommand "nixops-machines"
      { preferLocalBuild = true; }
      ''
        mkdir -p $out
        ${toString (lib.attrValues (lib.mapAttrs (n: v: ''
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
