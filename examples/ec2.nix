{

  webserver = 
    { config, pkgs, ... }:

    {
      services.httpd.enable = true;
      services.httpd.adminAddr = "e.dolstra@tudelft.nl";
      services.httpd.documentRoot = "${pkgs.valgrind}/share/doc/valgrind/html";
      
      deployment.targetEnv = "ec2";
      deployment.ec2.controller = https://ec2.us-east-1.amazonaws.com:443/;
      deployment.ec2.ami = "ami-d93bf4b0";
      deployment.ec2.instanceType = "m1.large";
      deployment.ec2.keyPair = "eelco";
      deployment.ec2.securityGroup = "eelco-test";
    };

}
