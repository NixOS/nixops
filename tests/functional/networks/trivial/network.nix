{
  network.description = "Test deployment";

  network.__test = # { pkgs }:
  {
    deploy = {
      commands = [
        { "nixops" = "deploy"; }
        # { cmd = "true"; }
        # { nixops = "deploy"; }
        # { exec = ["nixops" "ssh" "machine" "--" ]; }
        # { breakpoint = true; }
        # { breakpoint = "bash"; }
        # { cmd = "${pkgs.hello}/nixops deploy"; }
        # { cmd = "nixops ssh machine -- test -f /etc/ssh/authorized_keys.d/root"; }
      ];
    };
  };

  myhost =
    { resources, ... }:
    {
      imports = [
        ../../container/configuration.nix
      ];

      deployment.hasFastConnection = true;
      deployment.targetHost = "127.0.0.1";
      deployment.targetPort = 2024;
    };

}
