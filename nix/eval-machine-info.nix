{ system ? builtins.currentSystem
, networkExprs
}:

with import <nixos/lib/testing.nix> { inherit system; };
with pkgs;
with lib;

rec {

  networks = map (networkExpr: import networkExpr) networkExprs;

  network = zipAttrs networks;

  defaults = network.defaults or [];
  
  nodes =
    listToAttrs (map (machineName:
      let
        modules = getAttr machineName network;
      in
      { name = machineName;
        value = import <nixos/lib/eval-config.nix> {
          modules =
            modules ++
            defaults ++
            [ { key = "charon-stuff";
                # Make Charon's deployment.* options available.
                require = [ ./options.nix ];
                # Provide a default hostname and deployment target equal
                # to the attribute name of the machine in the model.
                networking.hostName = mkOverride 900 machineName;
                deployment.targetHost = mkOverride 900 machineName;
                environment.checkConfigurationOptions = false; # should only do this in phase 1
              }
            ];
          extraArgs = { inherit nodes; };
        };
      }
    ) (attrNames (removeAttrs network [ "network" "defaults" ])));

  # Phase 1: evaluate only the deployment attributes.
  info = {
  
    machines =
      flip mapAttrs nodes (n: v:
        { inherit (v.config.deployment) targetEnv targetHost encryptedLinksTo;
          adhoc = optionalAttrs (v.config.deployment.targetEnv == "adhoc") v.config.deployment.adhoc;
          ec2 = optionalAttrs (v.config.deployment.targetEnv == "ec2") v.config.deployment.ec2;
          virtualbox =
            let cfg = v.config.deployment.virtualbox; in
            optionalAttrs (v.config.deployment.targetEnv == "virtualbox") (cfg
              // { baseImage = if isDerivation cfg.baseImage then "drv" else toString cfg.baseImage; });
        }
      );

    network = fold (as: bs: as // bs) {} (network.network or []);

  };

  # Phase 2: build complete machine configurations.  
  machines = { names }:
    let nodes' = filterAttrs (n: v: elem n names) nodes; in 
    runCommand "vms"
      { preferLocalBuild = true; }
      ''
        mkdir -p $out
        ${toString (attrValues (mapAttrs (n: v: ''
          ln -s ${v.config.system.build.toplevel} $out/${n}
        '') nodes'))}
      '';

}
