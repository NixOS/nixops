import ./webdsldeploy/generate-network.nix {
  adminAddr = "foo@bar.com";  
  databasePassword = "admin";
  
  applications = [
    { name = "webdslorg";
      src = ./webdslorg;
      rootapp = true;
    }
  ];
  
  distribution = {
    test0 = {
      proxy = true;
    };
    
    test1 = {
      tomcat = true;
      httpd = true;
      mysqlMaster = true;
    };
      
    test2 = {
      tomcat = true;
      httpd = true;
      mysqlSlave = 2;
    };
  };
} //
{
  /*test3 = {pkgs, ...}: 
  {
    services = {
      xserver = {
        enable = true;
      
        displayManager = {
          slim.enable = false;
	  auto.enable = true;
        };
      
        windowManager = {
          default = "icewm";
          icewm = {
	    enable = true;
	  };
        };
      
        desktopManager.default = "none";
      };
    };
  
    environment = {
      systemPackages = [
        pkgs.mc
        pkgs.subversion
        pkgs.lynx
        pkgs.firefox
      ];
    };
  };*/
}
