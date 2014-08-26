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
        instanceType = "f1-micro";
        tags = [ "test" "instance" ];
        metadata.random = "mess";
      };
    };
}
