{
  network.description = "NixOS terminal server";

  machine = 
    { config, pkgs, modulesPath, ... }:

    {
      imports = [ "${modulesPath}/services/x11/terminal-server.nix" ];
    
      services.xserver.desktopManager.kde4.enable = true;
      services.xserver.desktopManager.xfce.enable = true;
      
      environment.systemPackages = [ pkgs.glxinfo pkgs.firefoxWrapper ];      
    };

}
