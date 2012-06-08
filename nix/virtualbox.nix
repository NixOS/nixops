{ config, pkgs, ... }:

with pkgs.lib;

{

  ###### interface

  options = {

    deployment.virtualbox.baseImage = mkOption {
      example = "/home/alice/base-disk.vdi";
      description = ''
        Path to the initial disk image used to bootstrap the
        VirtualBox instance.  The instance boots from a clone of this
        image.
      '';
    };

    deployment.virtualbox.memorySize = mkOption {
      default = 512;
      type = types.int;
      description = ''
        Memory size (M) of virtual machine.
      '';
    };

    deployment.virtualbox.headless = mkOption {
      default = false;
      description = ''
        If set, the VirtualBox instance is started in headless mode,
        i.e., without a visible display on the host's desktop.
      '';
    };

  };

  
  ###### implementation

  config = mkIf (config.deployment.targetEnv == "virtualbox") {

    nixpkgs.system = mkOverride 900 "x86_64-linux";

    deployment.virtualbox.baseImage = mkDefault (
      let
        unpack = name: sha256: pkgs.runCommand "virtualbox-charon-${name}.vdi" {}
          ''
            xz -d < ${pkgs.fetchurl {
              url = "http://nixos.org/releases/nixos/virtualbox-charon-images/virtualbox-charon-${name}.vdi.xz";
              inherit sha256;
            }} > $out
          '';
      in if config.nixpkgs.system == "x86_64-linux" then
        unpack "0.1pre33926-33924-x86_64" "0c9857e3955bb5af273375e85c0a62a50323ccfaef0a29b5eb7f1539077c1c40"
      else
        # !!! Stupid lack of laziness
        # throw "Unsupported VirtualBox system type!"
        ""
    );
        
  };

}
