let

  backend = 
    { config, pkgs, ... }:

    {
      services.httpd.enable = true;
      services.httpd.adminAddr = "e.dolstra@tudelft.nl";
      services.httpd.documentRoot = "${pkgs.valgrind}/share/doc/valgrind/html";
    };

in

{

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
            BalancerMember http://${nodes.backend1.config.networking.privateIPv4} retry=0
            BalancerMember http://${nodes.backend2.config.networking.privateIPv4} retry=0
          </Proxy>

          ProxyStatus       full
          ProxyPass         /server-status !
          ProxyPass         /       balancer://cluster/
          ProxyPassReverse  /       balancer://cluster/

          # For testing; don't want to wait forever for dead backend servers.
          ProxyTimeout      5
        '';
    };

  backend1 = backend;
  backend2 = backend;
  
}
