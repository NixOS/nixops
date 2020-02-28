{ ... } @ args:
let
  nixops = (import ./release.nix args).build."${builtins.currentSystem}";
in nixops
