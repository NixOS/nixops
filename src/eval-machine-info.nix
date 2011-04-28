{ nixpkgs ? builtins.getEnv "NIXPKGS_ALL"
, nixos ? builtins.getEnv "NIXOS"
, system ? builtins.currentSystem
, networkExpr
}:

with import "${nixos}/lib/testing.nix" { inherit nixpkgs system; };
with pkgs;

rec {
  x = complete { nodes = import networkExpr; testScript = ""; };
  
  machineInfo = builtins.attrNames (x.nodes);
  
  machines = runCommand "vms" {}
    ''
      mkdir -p $out
      ${toString (lib.attrValues (lib.mapAttrs (n: v: ''
        ln -s ${v.config.system.build.vm} $out/${n}
      '') x.nodes))}
    '';
}
