{
  network.description = "Mediawiki network";

  webserver = 
    { config, pkgs, ... }:

    with pkgs.lib;

    { services.httpd.enable = true;
      services.httpd.adminAddr = "e.dolstra@tudelft.nl";
      services.httpd.extraSubservices = singleton
        { serviceType = "mediawiki";
          siteName = "Example Wiki";
          dbServer = "database";
          logo = "http://nixos.org/logo/nix-wiki.png";
        };
      environment.systemPackages = [ pkgs.postgresql ];
      services.oidentd.enable = true;
    };

  database =
    { config, pkgs, nodes, ... }:

    with pkgs.lib;

    let

      # !!! Cut&paste, extremely ugly.
      # Unpack Mediawiki and put the config file in its root directory.
      mediawikiRoot = pkgs.stdenv.mkDerivation rec {
        name= "mediawiki-1.15.5";

        src = pkgs.fetchurl {
          url = "http://download.wikimedia.org/mediawiki/1.15/${name}.tar.gz";
          sha256 = "1d8afbdh3lsg54b69mnh6a47psb3lg978xpp277qs08yz15cjf7q";
        };

        buildPhase = "true";

        installPhase =
          ''
            mkdir -p $out
            cp -r * $out
          '';
      };

    in

    { services.postgresql.enable = true;
      services.postgresql.enableTCPIP = true;
      services.postgresql.authentication =
        ''
          local all root ident sameuser
          local mediawiki mediawiki ident mediawiki-map
          host  all root ${nodes.webserver.config.networking.privateIPv4}/32 ident sameuser
          host  mediawiki mediawiki ${nodes.webserver.config.networking.privateIPv4}/32 ident mediawiki-map
        '';
      services.postgresql.identMap =
        ''
          mediawiki-map root   mediawiki
          mediawiki-map wwwrun mediawiki
        '';

      jobs.init_mediawiki_db =
        { task = true;
          startOn = "started postgresql";
          script =
            ''
              mkdir -p /var/lib/psql-schemas
              if ! [ -e /var/lib/psql-schemas/mediawiki-created ]; then
                  ${pkgs.postgresql}/bin/createuser --no-superuser --no-createdb --no-createrole mediawiki
                  ${pkgs.postgresql}/bin/createdb mediawiki -O mediawiki
                  ( echo 'CREATE LANGUAGE plpgsql;'
                    cat ${mediawikiRoot}/maintenance/postgres/tables.sql
                    echo 'CREATE TEXT SEARCH CONFIGURATION public.default ( COPY = pg_catalog.english );'
                    echo COMMIT
                  ) | ${pkgs.postgresql}/bin/psql -U mediawiki mediawiki
                  touch /var/lib/psql-schemas/mediawiki-created
              fi
            '';
        };
      
      /*
      services.schemas = singleton
        { id = "mediawiki";
          database = "mediawiki";
          owner = "mediawiki";
          createOwner = true;
          definition = pkgs.mediawiki;
        };
      */
    };

}
