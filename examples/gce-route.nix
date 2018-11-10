/**
 * A typical scenario where we want to route all traffic to an EC2
 * machine through a NAT Gateway in GCE, only allowing the NAT Gateway IP
 * in the security group of the EC2 instance.
 *
 * This mainly deploy two machines, one in EC2 "ec2machine" and the other
 * one in GCE "nat-instance". The goal is to route all traffic in the
 * default network in GCE the through "nat-instance".
 *
 * The deployment of the Security Group isn't included in this example.
 */
let
   region = "us-east-1";
   zone = "us-east-1a";
in
{
  nat-instance =
    { pkgs, resources, lib, ... }:
    {
      deployment.targetEnv = "gce";
      deployment.gce = {
       canIpForward = true;
       region =  "us-central1-a";
      };
      networking.nat.enable = true;
    };

  resources.ec2KeyPairs.my-key-pair =
    { inherit region; };

  ec2machine =
    { resources, lib, ... }:
    {
      deployment.targetEnv = "ec2";
      deployment.ec2 = {
        inherit region zone;
        spotInstancePrice = 245;
        instanceType = "m4.large";
        associatePublicIpAddress = true;
        keyPair = resources.ec2KeyPairs.my-key-pair ;
      };
    };

  resources.gceRoutes.lb-default =
    { resources, ... }:
    {
      destination = resources.machines.ec2machine;
      priority = 800;
      nextHop = resources.machines.nat-instance;
      tags = [ "worker" ] ;
    };
}
