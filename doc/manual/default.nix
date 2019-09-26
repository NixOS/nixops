{ revision ? "local", nixpkgs ? <nixpkgs> }:

let

  pkgs = import nixpkgs { system = "x86_64-linux"; };

  systemModule = pkgs.lib.fixMergeModules [ ../../nix/options.nix ./dummy.nix ] {
                   inherit pkgs; utils = {};
                   resources = { gceImages.bootstrap = {}; };
                   name = "<name>"; uuid = "<uuid>";
                 };
  backwardsCompat = import ./compat.nix { inherit pkgs; };


in (pkgs.nixosOptionsDoc or backwardsCompat) {
  inherit (systemModule) options;
  inherit revision;
}
