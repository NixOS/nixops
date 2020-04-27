let
  pkgs = import <nixpkgs> {};
  nixos = import <nixpkgs/nixos> {
    configuration = ./configuration.nix;
  };

  inherit (pkgs) lib;

  systemDrv = nixos.config.system.build.toplevel;

  storeHash = drv: lib.head (lib.splitString "-" (lib.last (lib.splitString "/" drv)));

  name = nixos.config.networking.hostName + "-" + "image";

  tag = storeHash systemDrv;

in {
  image = "${name}:${tag}";
  inherit (nixos.config.system.build) tarball;

  dockerImage = pkgs.dockerTools.buildLayeredImage {
    inherit name tag;
    contents = [
      systemDrv
    ];
    extraCommands = ''
      rm etc
      mkdir -p proc sys dev etc
    '';
  };

}
