let
  region = "us-east-1";
in
{
  resources = {

    vpcRouteTables.route-table =
      { resources, ... }:
      { inherit region; vpcId = resources.vpc.vpc-test; };

    vpcRouteTableAssociations.association-test =
      { resources, ... }:
      {
        inherit region;
        subnetId = resources.vpcSubnets.subnet-test;
        routeTableId = resources.vpcRouteTables.route-table;
      };

    vpcRoutes.igw-route =
      { resources, ... }:
      {
        inherit region;
        routeTableId = resources.vpcRouteTables.route-table;
        destinationCidrBlock = "0.0.0.0/0";
        gatewayId = resources.vpcInternetGateways.igw-test;
      };

    vpcInternetGateways.igw-test =
      { resources, ... }:
      {
        inherit region;
        vpcId = resources.vpc.vpc-test;
      };
  };
}
