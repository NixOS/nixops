let
  region = "europe-west1-b";
in
{
  machine =
    { resources, ... }:
    {
      deployment.targetEnv = "gce";
      deployment.gce = {
        inherit region;
        instanceType = "g1-small";
        tags = [ "test" "instance" ];
        metadata.random = "mess";
      };
    };
}
