{
  network.description = "Test deployment";

  myhost =
    { resources, ... }:
    {
      imports = [
        ../container/configuration.nix
      ];

      deployment.hasFastConnection = true;
      deployment.targetHost = "127.0.0.1";
      deployment.targetPort = 2024;
    };

}
