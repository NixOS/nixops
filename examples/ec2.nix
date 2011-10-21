{

  webserver = 
    { config, pkgs, ... }:

    {
      services.httpd.enable = true;
      services.httpd.adminAddr = "e.dolstra@tudelft.nl";
      services.httpd.documentRoot = "${pkgs.valgrind}/share/doc/valgrind/html";
      
      deployment.targetEnv = "ec2";
      deployment.ec2.controller = https://ec2.eu-west-1.amazonaws.com:443/;
      deployment.ec2.ami = "ami-ecb49e98";
      deployment.ec2.instanceType = "m1.large";
      deployment.ec2.keyPair = "eelco";
    };

}
