{ module, revision ? "local", nixpkgs ? <nixpkgs> }:

let

  pkgs = import nixpkgs {};

  systemModule = pkgs.lib.fixMergeModules [ module ]
    { inherit pkgs; utils = {}; name = "<name>"; uuid = "<uuid>"; };

  backwardsCompat = import ./compat.nix { inherit pkgs; };

in ((pkgs.nixosOptionsDoc or backwardsCompat) {
  inherit (systemModule) options;
  inherit revision;
}).optionsDocBook
