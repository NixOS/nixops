{
  network.description = "Trivial test network";

  machine =
    { config, pkgs, ... }:
    { imports = [ ./nix-homepage.nix ]; };
}
