{

  webserver = 
    { config, pkgs, ... }:

    {
      services.httpd.enable = true;
      services.httpd.adminAddr = "e.dolstra@tudelft.nl";
      services.httpd.documentRoot = "${pkgs.valgrind}/share/doc/valgrind/html";
      
      deployment.targetEnv = "ec2";
      deployment.ec2.type = "nova";
      deployment.ec2.controller = http://192.168.1.20:8773/services/Cloud;
      deployment.ec2.ami = "ami-nixos";
      deployment.ec2.instanceType = "m1.large";
      deployment.ec2.keyPair = "my_key";
    };

}
