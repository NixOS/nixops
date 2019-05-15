{ region ? "us-east-1"
, accessKeyId ? "testing"
, ...
}:
{
  resources.ec2LaunchTemplate.testlaunchtemplate =
    {
      inherit region accessKeyId;
      name = "lt-with-nixops";
      description = "lt with nix";
      versionDescription = "version 1 ";
      LTData = {
        imageId = "ami-009c9c3f1af480ff3";
        keyName = "dovah.kin";
      };

    };
}
