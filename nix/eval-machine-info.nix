{ system ? builtins.currentSystem
, networkExprs
, flakeUri ? null
, flake ? if flakeUri == null then null else builtins.getFlake flakeUri
, checkConfigurationOptions ? true
, uuid
, deploymentName
, args
, pluginNixExprs
}:

let
  importedPluginNixExprs = map import pluginNixExprs;
  flakeExpr = flake.outputs.nixopsConfigurations.default or { };

  nixpkgsBoot = <nixpkgs> ; # this will be replaced on install by nixops' nixpkgs input
  libOf = nixpkgs: import /${nixpkgs}/lib;
  libBoot = libOf nixpkgsBoot;

  evalMod = lib: mod: lib.evalModules {
    specialArgs = args // { inherit lib system; };
    modules = networkExprs ++ [
      ./net.nix mod flakeExpr
      {
        nixpkgs = lib.mkDefault flake.inputs.nixpkgs or nixpkgsBoot;
        network.nodeExtraArgs = { inherit uuid deploymentName; };
        # Make NixOps's deployment.* options available.
        deployment = {
          name = deploymentName;
          arguments = args;
          inherit uuid;
        };
        defaults = {
          imports = lib.lists.concatMap (e: e.options) importedPluginNixExprs;
          environment.checkConfigurationOptions = lib.mkOverride 900 checkConfigurationOptions;
        };
      }
    ];
  };

  inherit ((evalMod libBoot { _module.check = false; }).config) nixpkgs;
  pkgs = nixpkgs.legacyPackages.${system} or (import nixpkgs { inherit system; });
  lib = nixpkgs.lib or pkgs.lib or (builtins.tryEval (libOf nixpkgs)).value or libBoot;

in rec {
  inherit nixpkgs;
  net = evalMod lib {
    resources.imports = pluginResourceModules;
    network.resourcesDefaults._module.args = { inherit pkgs uuid; };
  };

  # for backward compatibility
  network = lib.mapAttrs (n: v: [v]) net.config;
  networks = [ net.config ];
  defaults = [ net.config.defaults ];
  nodes = #TODO: take options and other modules outputs for each node
    lib.mapAttrs (n: v: {
      config = v;
      options = net.options.nodes.${n};
      inherit (v.nixpkgs) pkgs;
    }) net.config.nodes;

  # ./resource.nix is imported in resource opt but does not define resource types
  # we have to remove those entries as they do not otherwise conform to the resource schema
  resources =  removeAttrs net.config.resources (lib.concatMap
    (e: lib.attrNames (import e { name = ""; inherit lib; }).options)
    [ ./resource.nix ./default-deployment.nix ]);

  pluginResources = map (e: e.resources) importedPluginNixExprs;
  pluginDeploymentConfigExporters = lib.lists.concatMap (e: e.config_exporters {
    inherit pkgs;
    inherit (lib) optionalAttrs;
  }) importedPluginNixExprs;

  # Compute the definitions of the non-machine resources.
  resourcesByType = lib.zipAttrs (network.resources or []);

  pluginResourceModules = lib.lists.concatMap (lib.mapAttrsToList toResourceModule) pluginResourceLegacyReprs;

  toResourceModule = k: { _type, resourceModule }:
    {
      options.${k} = lib.mkOption {
        type = lib.types.attrsOf (lib.types.submodule resourceModule);
        default = { /* no resources configured */ };
      };
    };

  pluginResourceLegacyReprs =
    (map
      (f:
        lib.mapAttrs
          validateLegacyRepr
          (f {
            inherit evalResources resourcesByType lib;
            inherit (lib) zipAttrs;
          })
      )
      pluginResources
    );

  validateLegacyRepr = k: v:
    if v._type or null == "legacyResourceRepresentation" then
      v
    else
      throw
      ''Legacy plugin resources are only supported if they follow the pattern:

            resources = { evalResources, zipAttrs, resourcesByType, ... }: {
              foos = evalResources ./foo.nix (zipAttrs resourcesByType.foos or []);
              # ...
            };

        The resource ${k} did not follow that pattern. Please update the
        corresponding plugin to declare the resource submodule directly instead.
      '';

  # NOTE: this is a legacy name. It does not invoke the module system,
  #       but rather preserves one argument, so that it can be turned
  #       into a proper submodule later.
  evalResources = resourceModule: _: {
    _type = "legacyResourceRepresentation";
    inherit resourceModule;
  };

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
      [ "nixpkgs" "resourcesDefaults" "nodesExtraArgs" ]  # Not serialisable
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

  exprToArgs = nixopsExpr: f:
    if builtins.isFunction nixopsExpr then
      map (a: { "${a}" = builtins.toString f; } ) (builtins.attrNames (builtins.functionArgs nixopsExpr))
    else [];

  fileToArgs = f:
    let
      nixopsExpr = import f;
    in
      if builtins.isFunction nixopsExpr then
        map (a: { "${a}" = builtins.toString f; } ) (builtins.attrNames (builtins.functionArgs nixopsExpr))
      else [];

  getNixOpsArgs = fs: lib.zipAttrs (lib.unique (lib.concatMap fileToArgs (getNixOpsExprs fs)));

  nixopsArguments =
    if flakeUri == null then getNixOpsArgs networkExprs
    else lib.listToAttrs (builtins.map (a: {name = a; value = [ flakeUri ];}) (lib.attrNames (builtins.functionArgs flakeExpr)));

}
