{ nixopsSrc ? { outPath = ./.; revCount = 0; shortRev = "abcdef"; rev = "HEAD"; }
, officialRelease ? false
}:

let

  channel = "nixos-16.09";
  sysPkgs = import <nixpkgs> {};
  # Use `runCommand` to grab the SHA of the latest build of the channel. This
  # ensures that the `nixpkgs` set we end up with has already passed through
  # Hydra and therefore has passed its tests and has a binary cache available.
  latestRevision = import (sysPkgs.runCommand "latestRevision"
    { buildInputs = [ sysPkgs.wget ];
      # Force the input to be different each time or else Nix won't check for
      # updates to the channel next time we evaluate this expression
      dummy = builtins.currentTime;
    }
    ''
      SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.crt
      # nixos.org/channels/$channel always points to the latest released
      # revision of the channel, which contains a file with its git SHA. Once we
      # have it, we have to wrap it in quotes so it will become a string when we
      # `import` $out
      wget -O - https://nixos.org/channels/${channel}/git-revision |\
        sed 's#\(.*\)#"\1"#' > $out
    '');
  # Now that we have the SHA we can just use Github to get the tarball and thus
  # the `nixpkgs` expressions
  pkgs = import (fetchTarball
    "https://github.com/NixOS/nixpkgs-channels/archive/${latestRevision}.tar.gz"
  ) {};

  version = "1.5" + (if officialRelease then "" else "pre${toString nixopsSrc.revCount}_${nixopsSrc.shortRev}");

  # _aioamqp = with python35Packages; buildPythonPackage {
  #   name = "aioamqp-0.4.0";
  #   src = fetchurl {
  #     url = "https://pypi.python.org/packages/source/a/aioamqp/aioamqp-0.4.0.tar.gz";
  #     sha256 = "4882ca561f1aa88beba3398c8021e7918605c371f4c0019b66c12321edda10bf";
  #   };
  # };
#   requestsNew = with pkgs.python2Packages; buildPythonPackage rec {
#     # name = "requests-1.2.3";
#     name = "requests-2.11.1";
#     # disabled = !pythonOlder "3.4";

#     src = pkgs.fetchurl {
#       url = "mirror://pypi/r/requests/${name}.tar.gz";
#       # sha256 = "156bf3ec27ba9ec7e0cf8fbe02808718099d218de403eb64a714d73ba1a29ab1";
#       sha256 = "0cx1w7m4cpslxz9jljxv0l9892ygrrckkiwpp2hangr8b01rikss";
# # 0cx1w7m4cpslxz9jljxv0l9892ygrrckkiwpp2hangr8b01rikss
#     };
#     doCheck = false;

#     meta = {
#       description = "An Apache2 licensed HTTP library, written in Python, for human beings";
#       homepage = http://docs.python-requests.org/en/latest/;
#     };
#   };

#   digital-ocean = with pkgs.python2Packages; buildPythonPackage rec {
#     name = "python-digitalocean-1.10.1";
#     doCheck = false;
#     propagatedBuildInputs = [requestsNew];
#     src = pkgs.fetchurl {
#       url = "mirror://pypi/p/python-digitalocean/${name}.tar.gz";

#       # url = "https://pypi.python.org/packages/0a/4c/85ff7c732bf7f50caf81d31f71c4293153831705bdbd0fc29152abb567b6/${name}.tar.gz";
#       sha256 = "12qybflfnl08acspz7rpaprmlabgrzimacbd7gm9qs5537hl3qnp";
#       # sha256 = "1zycy149avwvwzbx2xg9rpxnra3sk9z6l43crv2zp4a1dr3jhakw";

# # https://pypi.python.org/packages/0a/4c/85ff7c732bf7f50caf81d31f71c4293153831705bdbd0fc29152abb567b6/python-digitalocean-1.10.1.tar.gz
#     };
#   };


in

rec {

  tarball = pkgs.releaseTools.sourceTarball {
    name = "nixops-tarball";

    src = nixopsSrc;

    inherit version;

    officialRelease = true; # hack

    buildInputs = [ pkgs.git pkgs.libxslt pkgs.docbook5_xsl ];

    postUnpack = ''
      # Clean up when building from a working tree.
      if [ -d $sourceRoot/.git ]; then
        (cd $sourceRoot && (git ls-files -o | xargs -r rm -v))
      fi
    '';

    distPhase =
      ''
        # Generate the manual and the man page.
        cp ${import ./doc/manual { revision = nixopsSrc.rev; }} doc/manual/machine-options.xml
        ${pkgs.lib.concatMapStrings (fn: ''
          cp ${import ./doc/manual/resource.nix { revision = nixopsSrc.rev; module = ./nix + ("/" + fn + ".nix"); }} doc/manual/${fn}-options.xml
        '') [ "ebs-volume" "sns-topic" "sqs-queue" "ec2-keypair" "s3-bucket" "iam-role" "ssh-keypair" "ec2-security-group" "elastic-ip"
              "gce-disk" "gce-image" "gce-forwarding-rule" "gce-http-health-check" "gce-network"
              "gce-static-ip" "gce-target-pool" "gse-bucket"
              "datadog-monitor" "datadog-timeboard" "datadog-screenboard"
              "azure-availability-set" "azure-blob-container" "azure-blob" "azure-directory"
              "azure-dns-record-set" "azure-dns-zone" "azure-express-route-circuit"
              "azure-file" "azure-gateway-connection" "azure-load-balancer" "azure-local-network-gateway"
              "azure-network-security-group" "azure-queue" "azure-reserved-ip-address"
              "azure-resource-group" "azure-share" "azure-storage" "azure-table"
              "azure-traffic-manager-profile"
              "azure-virtual-network" "azure-virtual-network-gateway"]}

        for i in scripts/nixops setup.py doc/manual/manual.xml; do
          substituteInPlace $i --subst-var-by version ${version}
        done

        make -C doc/manual install docdir=$out/manual mandir=$TMPDIR/man

        releaseName=nixops-$VERSION
        mkdir ../$releaseName
        cp -prd . ../$releaseName
        rm -rf ../$releaseName/.git
        mkdir $out/tarballs
        tar  cvfj $out/tarballs/$releaseName.tar.bz2 -C .. $releaseName

        echo "doc manual $out/manual manual.html" >> $out/nix-support/hydra-build-products
      '';
  };

  build = pkgs.lib.genAttrs [ "x86_64-linux" "i686-linux" "x86_64-darwin" ] (system:
    # with import <nixpkgs> { inherit system; };
    with import (fetchTarball
      "https://github.com/NixOS/nixpkgs-channels/archive/${latestRevision}.tar.gz"
    ) { inherit system; };
    # with import pkgs { inherit system; };

    python2Packages.buildPythonPackage rec {
      name = "nixops-${version}";
      namePrefix = "";

      src = "${tarball}/tarballs/*.tar.bz2";

      buildInputs = [ python2Packages.nose python2Packages.coverage ];

      propagatedBuildInputs = with python2Packages;
        [
          prettytable
          boto
          boto3
          hetzner
          libcloud
          azure-storage
          azure-mgmt-compute
          azure-mgmt-network
          azure-mgmt-resource
          azure-mgmt-storage
          adal
          # Go back to sqlite once Python 2.7.13 is released
          pysqlite
          datadog
          digital-ocean
        ];

      # For "nix-build --run-env".
      shellHook = ''
        export PYTHONPATH=$(pwd):$PYTHONPATH
        export PATH=$(pwd)/scripts:${openssh}/bin:$PATH
      '';

      doCheck = true;

      # Needed by libcloud during tests
      SSL_CERT_FILE = "${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt";

      postInstall =
        ''
          # Backward compatibility symlink.
          ln -s nixops $out/bin/charon

          make -C doc/manual install \
            docdir=$out/share/doc/nixops mandir=$out/share/man

          mkdir -p $out/share/nix/nixops
          cp -av nix/* $out/share/nix/nixops

          # Add openssh to nixops' PATH. On some platforms, e.g. CentOS and RHEL
          # the version of openssh is causing errors when have big networks (40+)
          wrapProgram $out/bin/nixops --prefix PATH : "${openssh}/bin"
        ''; # */

      meta.description = "Nix package for ${stdenv.system}";
    });

  # This is included here, so it's easier to fetch by the newly installed
  # Hetzner machine directly instead of waiting for ages if you have a
  # connection with slow upload speed.
  hetznerBootstrap = import ./nix/hetzner-bootstrap.nix;

  tests.none_backend = (import ./tests/none-backend.nix {
    nixops = build.x86_64-linux;
    system = "x86_64-linux";
  }).test;

  tests.hetzner_backend = (import ./tests/hetzner-backend {
    nixops = build.x86_64-linux;
    system = "x86_64-linux";
  }).test;
}
