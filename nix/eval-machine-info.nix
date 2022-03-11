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
  flakeExpr = (builtins.tryEval flake.outputs.nixopsConfigurations.default).value or { };

  nixpkgsBoot = toString <nixpkgs> ; # this will be replaced on install by nixops' nixpkgs input
  libBoot = import "${nixpkgsBoot}/lib";

  baseMods = lib: [
    {
      options.nixpkgs = lib.mkOption {
        type = lib.types.path;
        description = "Path to the nixpkgs instance used to buld the machines.";
        defaultText = lib.literalDocBook "The 'nixpkgs' input to either the provided flake or nixops' own.";
        default = (builtins.tryEval flake.inputs.nixpkgs).value or nixpkgsBoot;
      };
      config._module.freeformType = with lib.types;attrsOf anything;
    }
    flakeExpr
  ] ++ networkExprs;

  evalBoot = libBoot.evalModules {
    specialArgs = args;
    modules = baseMods libBoot;
  };

  inherit (evalBoot.config) nixpkgs;

  pkgs = (builtins.tryEval nixpkgs.legacyPackages.${system}).value or (import nixpkgs { inherit system; });
  lib = nixpkgs.lib or pkgs.lib or (builtins.tryEval (import "${nixpkgs}/lib")).value or libBoot;

  inherit (lib) mkOption types;
in rec {
  inherit nixpkgs;

  net = lib.evalModules {
    specialArgs = args;
    modules = baseMods lib ++ [
      ({ config, options, ... }: {
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
              default = {};
            };
          };
          resources = mkOption {
            default = {};
            type = types.submoduleWith {
              modules = [{
                options = let
                  resOpt = mainModule: mkOption {
                    default = {};
                    type = types.attrsOf (types.submodule (r:{
                      _module.args = {
                        inherit pkgs uuid;
                        resources = r.config;
                        # inherit nodes, essentially
                        nodes =
                          lib.mapAttrs
                            (nodeName: node:
                              lib.mapAttrs
                                (key: lib.warn "Resource ${r.name} accesses nodes.${nodeName}.${key}, which is deprecated. Use the equivalent option instead: nodes.${nodeName}.${newOpt key}.")
                                config.nodes.${nodeName})
                            config.nodes;
                      };
                      imports = [
                        mainModule
                        deploymentInfoModule
                        ./resource.nix
                      ];
                    }));
                  };
                in {
                  sshKeyPairs = resOpt ./ssh-keypair.nix;
                  commandOutput = resOpt ./command-output.nix;
                };
                config = {
                  machines = config.nodes;
                  _module.check = false;
                };
              }] ++ pluginResources;
              specialArgs = {
                inherit evalResources resourcesByType lib;
                inherit (lib) zipAttrs;
              };
            };
          };
          # Compute the definitions of the machines.
          nodes = mkOption {
            description = "The NixOS configurations for the nodes in the network.";
            type = types.attrsOf (import "${nixpkgs}/nixos/lib/eval-config.nix" {
              specialArgs = {
                inherit uuid deploymentName;
                inherit (config) nodes resources;
              } // config.network.nodesExtraArgs;
              modules =
                config.defaults ++
                # Make NixOps's deployment.* options available.
                pluginOptions ++
                [
                  ./options.nix
                  ./resource.nix
                  deploymentInfoModule
                  ({ name, ... }: rec{
                    _file = ./eval-machine-info.nix;
                    key = _file;
                    # Provide a default hostname and deployment target equal
                    # to the attribute name of the machine in the model.
                    networking.hostName = lib.mkOverride 900 name;
                    deployment.targetHost = lib.mkOverride 900 name;
                    environment.checkConfigurationOptions = lib.mkOverride 900 checkConfigurationOptions;
                    nixpkgs.system = lib.mkDefault system;
                  })
                ];
            }).type;
          };
          defaults = mkOption {
            type = with lib; mkOptionType {#TODO: remove after merging https://github.com/NixOS/nixpkgs/pull/163617
              name = "deferredModule";
              description = "module";
              check = t: isAttrs t || isFunction t || builtins.isPath t;
              merge = loc: defs: map (def: lib.setDefaultModuleLocation "${showOption loc} from ${def.file}" def.value) defs;
            };
            # type = types.deferredModule;
            default = { };
            description = ''
              Extra NixOS options to add to all nodes.
            '';
          };
        };
        config = let
          nodes = removeAttrs config (builtins.attrNames options);
        in lib.mkIf ({} != nodes) { #TODO: actual warning/assert module impl.
          nodes = lib.warn "Please use the actual nodes.* option instead of assigning machines to the config's top level" nodes;
        };
      })
    ];
  };

  inherit (net.config) resources;
  defaults = [ net.config.defaults ];
  #TODO: take options and other modules outputs for each node
  nodes =
    lib.mapAttrs (n: v: {
      config = v;
      options = net.options.nodes.${n};
      inherit (v.nixpkgs) pkgs;
    }) net.config.nodes;

  # for backward compatibility
  network = lib.mapAttrs (n: v: [v]) net.config;
  networks = [ net.config ];

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
