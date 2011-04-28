{ nixpkgs ? builtins.getEnv "NIXPKGS_ALL"
, nixos ? builtins.getEnv "NIXOS"
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
                networking.hostName = pkgs.lib.mkOverride 900 configurationName;
                deployment.targetHost = pkgs.lib.mkOverride 900 configurationName;
                networking.firewall.enable = pkgs.lib.mkOverride 900 false; # hack, think about this later
              }
            ];
          extraArgs = { inherit nodes; };
        };
      }
    ) (attrNames network));

  machineInfo = builtins.attrNames nodes;
  
  machines = runCommand "vms" {}
    ''
      mkdir -p $out
      ${toString (lib.attrValues (lib.mapAttrs (n: v: ''
        ln -s ${v.config.system.build.toplevel} $out/${n}
      '') nodes))}
    '';
}
