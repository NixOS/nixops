{
   resources.elasticIPs.nat-eip =
   {
     region = "us-east-1";
     vpc = true;
   };

   resources.vpcNatGateways.nat =
     { resources, ... }:
     {
       region = "us-east-1";
       allocationId = resources.elasticIPs.nat-eip;
       subnetId = resources.vpcSubnets.subnet-test;
     };
 }
