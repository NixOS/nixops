{ region ? "us-east-1"
, ...
}:

{
resources.ec2SecurityGroups =
  {
   securityGroup1 = {
        inherit region;
        name = "securityGroup1";
        description = "securityGroup1 description";
        rules = [
          { fromPort = 22; toPort = 22; protocol = "tcp"; sourceIp = "19.10.19.93/30"; }
          { fromPort = 80; toPort = 8080; protocol = "tcp"; sourceIp = "55.55.55.55/32"; }
        ];
      };
     securityGroup2 = {
        inherit region;
        name = "securityGroup2";
        description = "securityGroup2 description";
        rules = [
          { fromPort = 22; toPort = 22; sourceIp = "6.6.6.6"; }
          { fromPort = 80; toPort = 80; sourceIp = "55.55.5.5/20"; }
        ];
      };
   };
}

