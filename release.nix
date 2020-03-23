{ nixopsSrc ? { outPath = ./.; revCount = 0; shortRev = "abcdef"; rev = "HEAD"; }
, officialRelease ? false
, nixpkgs ? <nixpkgs>
, p ? (p: [ ])
}:

let
  pkgs = import nixpkgs { config = {}; overlays = []; };
  version = "1.8" + (if officialRelease then "" else "pre${toString nixopsSrc.revCount}_${nixopsSrc.shortRev}");

in rec {

  allPlugins = let
    plugins = let
      allPluginVers = import ./data.nix;
      fetch = v:
        pkgs.fetchFromGitHub {
          inherit (v) owner repo sha256;
          rev = "v${v.version}";
        };
      srcDrv = v: (fetch v) + "/release.nix";
    in self: let
      rawPlugins = (builtins.mapAttrs (n: v: self.callPackage (srcDrv allPluginVers.${n}) {}) allPluginVers);
    in rawPlugins // { inherit nixpkgs; nixops = buildWithNoPlugins; };
  in pkgs.lib.makeScope pkgs.newScope plugins;

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

    distPhase = ''
      # Generate the manual and the man page.
      cp ${(import ./doc/manual { revision = nixopsSrc.rev; inherit nixpkgs; }).optionsDocBook} doc/manual/machine-options.xml

      for i in nixops/__main__.py setup.py doc/manual/manual.xml; do
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

  build = buildWithPlugins p;
  buildWithNoPlugins = buildWithPlugins (_: []);
  buildWithPlugins = pluginSet: pkgs.lib.genAttrs [ "x86_64-linux" "i686-linux" "x86_64-darwin" ] (system:
    let
      pkgs = import nixpkgs { inherit system; };
      pythonPackages = pkgs.python37Packages;
    in pythonPackages.buildPythonApplication rec {
      name = "nixops-${version}";

      src = "${tarball}/tarballs/*.tar.bz2";

      buildInputs = [ pythonPackages.nose pythonPackages.coverage ];

      nativeBuildInputs = [
        (pythonPackages.mypy.overrideAttrs ({ propagatedBuildInputs, ... }: {
          propagatedBuildInputs = propagatedBuildInputs ++ [
            pythonPackages.lxml
          ];
        }))
        pythonPackages.black
      ];

        propagatedBuildInputs = [
          pythonPackages.prettytable
          pythonPackages.pluggy
          pythonPackages.typing-extensions
        ] ++ pkgs.lib.traceValFn
           (x: "Using plugins: " + builtins.toJSON x)
           (map (d: d.build.${system}) (pluginSet allPlugins));

      # For "nix-build --run-env".
      shellHook = ''
        export PYTHONPATH=$(pwd):$PYTHONPATH
        export PATH=$(pwd)/scripts:${pkgs.openssh}/bin:$PATH
      '';

      doCheck = true;

      postCheck = ''
        # smoke test
        HOME=$TMPDIR $out/bin/nixops --version
      '';

      # Needed by libcloud during tests
      SSL_CERT_FILE = "${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt";

      # Add openssh to nixops' PATH. On some platforms, e.g. CentOS and RHEL
      # the version of openssh is causing errors when have big networks (40+)
      makeWrapperArgs = ["--prefix" "PATH" ":" "${pkgs.openssh}/bin" "--set" "PYTHONPATH" ":"];

      postInstall = ''
        # Backward compatibility symlink.
        ln -s nixops $out/bin/charon

        make -C doc/manual install \
          docdir=$out/share/doc/nixops mandir=$out/share/man

        mkdir -p $out/share/nix/nixops
        cp -av nix/* $out/share/nix/nixops
      '';

      meta.description = "Nix package for ${pkgs.stdenv.system}";
    });

  /*
  tests.none_backend = (import ./tests/none-backend.nix {
    nixops = build.x86_64-linux;
    system = "x86_64-linux";
  }).test;
  */
}
