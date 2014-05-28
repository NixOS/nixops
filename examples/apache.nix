let

  backend =
    { config, pkgs, ... }:
    { imports = [ ./nix-homepage.nix ];
      networking.firewall.allowedTCPPorts = [ 80 ];
    };

in

{
  network.description = "Load balancer test";

  proxy =
    { config, pkgs, nodes, ... }:

    {
      services.httpd.enable = true;
      services.httpd.adminAddr = "e.dolstra@tudelft.nl";
      services.httpd.extraModules = ["proxy_balancer"];

      services.httpd.extraConfig =
        ''
          ExtendedStatus on

          <Location /server-status>
            Order deny,allow
            Allow from all
            SetHandler server-status
          </Location>

          <Proxy balancer://cluster>
            Allow from all
            BalancerMember http://backend1 retry=0
            BalancerMember http://backend2 retry=0
          </Proxy>

          ProxyStatus       full
          ProxyPass         /server-status !
          ProxyPass         /       balancer://cluster/
          ProxyPassReverse  /       balancer://cluster/

          # For testing; don't want to wait forever for dead backend servers.
          ProxyTimeout      5
        '';

      networking.firewall.allowedTCPPorts = [ 80 ];
    };

  backend1 = backend;
  backend2 = backend;
}
