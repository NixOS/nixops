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

  zipAttrs = set: builtins.listToAttrs (
    map (name: { inherit name; value = builtins.catAttrs name set; }) (builtins.concatMap builtins.attrNames set));

  flake = builtins.getFlake flakeUri;
  flakeExpr = flake.outputs.nixopsConfigurations.default or { };

  nixpkgsBoot = toString <nixpkgs> ; # this will be replaced on install by nixops' nixpkgs input
  libBoot = import "${nixpkgsBoot}/lib";

  evalModules = lib: modules: lib.evalModules {
    specialArgs = args // { inherit lib system; };
    modules = modules ++ networkExprs ++ [
      flakeExpr
      {
        options.nixpkgs = lib.mkOption {
          type = lib.types.path;
          description = "Path to the nixpkgs instance used to buld the machines.";
          defaultText = lib.literalDocBook "The 'nixpkgs' input to either the provided flake or nixops' own.";
          default = flake.inputs.nixpkgs or nixpkgsBoot;
        };
      }
    ];
  };

  inherit ((evalModules libBoot [{
    _module.freeformType = with libBoot.types;attrsOf anything;
  }]).config) nixpkgs;

  pkgs = nixpkgs.legacyPackages.${system} or (import nixpkgs { inherit system; });
  lib = nixpkgs.lib or pkgs.lib or (builtins.tryEval (import "${nixpkgs}/lib")).value or libBoot;
  inherit (lib) mkOption types;

in rec {
  inherit nixpkgs;

  net = evalModules lib [
    ./net.nix
    ({config, ...}:{
      options.resources = mkOption {
        default = { };
        type = types.submoduleWith {
          modules = [(r:{
            options =
              let
                resOpt = mainModule: mkOption {
                  default = { };
                  type = types.attrsOf (types.submodule {
                    _module.args = {
                      inherit pkgs uuid;
                      resources = r.config;
                      # inherit nodes, essentially
                      nodes =
                        lib.mapAttrs
                          (nodeName: node:
                            lib.mapAttrs
                              (key: lib.warn
                                "Resource ${r.name} accesses nodes.${nodeName}.${key}, which is deprecated. Use the equivalent option instead: nodes.${nodeName}.${newOpt key}.")
                              config.nodes.${nodeName})
                          config.nodes;
                    };
                    imports = [
                      mainModule
                      deploymentInfoModule
                      ./resource.nix
                    ];
                  });
                };
              in
              {
                sshKeyPairs = resOpt ./ssh-keypair.nix;
                commandOutput = resOpt ./command-output.nix;
              };
            config = {
              machines = config.nodes;
              _module.check = false;
            };
          })] ++ pluginResources;
          specialArgs = {
            inherit evalResources resourcesByType lib;
            inherit (lib) zipAttrs;
          };
        };
      };
    })
    {
      network.nodeExtraArgs = {
        inherit uuid deploymentName;
      };
      defaults.environment.checkConfigurationOptions = lib.mkOverride 900 checkConfigurationOptions;
      # Make NixOps's deployment.* options available.
      defaults.imports = pluginOptions ++ [ deploymentInfoModule ];
    }
  ];

  # for backward compatibility
  network = lib.mapAttrs (n: v: [v]) net.config;
  networks = [ net.config ];

  inherit (net.config) resources;
  defaults = [ net.config.defaults ];
  nodes = #TODO: take options and other modules outputs for each node
    lib.mapAttrs (n: v: {
      config = v;
      options = net.options.nodes.${n};
      inherit (v.nixpkgs) pkgs;
    }) net.config.nodes;

  importedPluginNixExprs = map
    (expr: import expr)
    pluginNixExprs;
  pluginOptions = lib.foldl (a: e: a ++ e.options) [ ] importedPluginNixExprs;
  pluginResources = map (e: e.resources) importedPluginNixExprs;
  pluginDeploymentConfigExporters = (lib.foldl
    (a: e: a ++ (e.config_exporters {
      inherit pkgs;
      inherit (lib) optionalAttrs;
    })) [ ]
    importedPluginNixExprs);

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
    lib.mapAttrs
      (name: defs:
        let
          # Arguments fed to all modules
          moduleArgs = {
            _module.args = {
              inherit pkgs uuid name resources;

              # inherit nodes, essentially
              nodes =
                lib.mapAttrs
                  (nodeName: node:
                    lib.mapAttrs
                      (key: lib.warn "Resource ${name} accesses nodes.${nodeName}.${key}, which is deprecated. Use the equivalent option instead: nodes.${nodeName}.${newOpt key}.")
                      info.machines.${nodeName}
                    // node)
                  nodes;
            };
          };
          modules = [
            moduleArgs
            mainModule
            deploymentInfoModule
            ./resource.nix
          ] ++ defs;
        in
          builtins.removeAttrs
            (lib.evalModules { inherit modules; }).config
            ["_module"])
      _resources;

  newOpt = key: {
    nixosRelease = "config.system.nixos.release and make sure it is set properly";
    publicIPv4 = "config.networking.publicIPv4";
  }.${key} or "config.deployment.${key}";

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
