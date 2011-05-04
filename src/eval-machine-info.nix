{ nixpkgs ? builtins.getEnv "NIXPKGS_ALL"
, nixos ? if builtins.getEnv "NIXOS" == "" then /etc/nixos/nixos else builtins.getEnv "NIXOS"
, system ? builtins.currentSystem
, networkExprs
}:

with import "${nixos}/lib/testing.nix" { inherit nixpkgs system; };
with pkgs;
with lib;

rec {

  networks = map (networkExpr: import networkExpr) networkExprs;

  network = zipAttrs networks;
  
  nodes =
    listToAttrs (map (configurationName:
      let
        modules = getAttr configurationName network;
      in
      { name = configurationName;
        value = import "${nixos}/lib/eval-config.nix" {
          inherit nixpkgs;
          modules =
            modules ++
            [ # Slurp in the required configuration for machines in the adhoc cloud.
              /home/eelco/Dev/configurations/tud/cloud/cloud-vm.nix
              # Provide a default hostname and deployment target equal
              # to the attribute name of the machine in the model.
              { key = "set-default-hostname";
                networking.hostName = mkOverride 900 configurationName;
                deployment.targetHost = mkOverride 900 configurationName;
                networking.firewall.enable = mkOverride 900 false; # hack, think about this later
                environment.checkConfigurationOptions = false; # should only do this in phase 1
              }
            ];
          extraArgs = { inherit nodes; };
        };
      }
    ) (attrNames network));

  # Phase 1: evaluate only the deployment attributes.
  machineInfo =
    flip mapAttrs nodes (n: v:
      { inherit (v.config.deployment) targetEnv targetHost;
        adhoc = optionalAttrs (v.config.deployment.targetEnv == "adhoc") v.config.deployment.adhoc;
      }
    );

  # Phase 2: build complete machine configurations.  
  machines = runCommand "vms" {}
    ''
      mkdir -p $out
      ${toString (attrValues (mapAttrs (n: v: ''
        ln -s ${v.config.system.build.toplevel} $out/${n}
      '') nodes))}
    '';
}
