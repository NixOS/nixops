{
  network.description = "Trivial test network";

  webserver = 
    { config, pkgs, ... }:

    {
      services.httpd.enable = true;
      services.httpd.adminAddr = "e.dolstra@tudelft.nl";
      services.httpd.documentRoot = "${pkgs.valgrind}/share/doc/valgrind/html";
      
      deployment.targetEnv = "ec2";
      deployment.ec2.region = "us-east-1";
      deployment.ec2.instanceType = "m1.large";
      deployment.ec2.keyPair = "eelco";
      deployment.ec2.securityGroups = [ "eelco-test" ];
    };

}
