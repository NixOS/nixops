{
  network.description = "Trivial test network";

  machine = 
    { config, pkgs, ... }:
    { require = [ ./nix-homepage.nix ]; };
}
