let
  pkgs = import <nixpkgs> {};
  nixos = import <nixpkgs/nixos> {
    configuration = ./configuration.nix;
    system = "x86_64-linux";
  };
in
pkgs.dockerTools.buildLayeredImage {
  name = nixos.config.networking.hostName + "-" + "image";
  tag = "latest";
  contents = [
    nixos.config.system.build.toplevel
  ];
  extraCommands = ''
   rm etc
   mkdir -p proc sys dev etc
 '';
}
