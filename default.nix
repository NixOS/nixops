{ nixpkgs ? <nixpkgs>
, pkgs ? import nixpkgs {}
, poetry2nix ? pkgs.poetry2nix
, symlinkJoin ? pkgs.symlinkJoin
, lib ? pkgs.lib
, runCommandNoCC ? pkgs.runCommandNoCC
, overrides ? (self: super: {})
}:

let
  # Wrap the buildEnv derivation in an outer derivation that omits interpreters & other binaries
  mkPluginDrv = {
    finalDrv
    , interpreter
    , plugins
  }: let

    # The complete buildEnv drv
    buildEnvDrv = interpreter.buildEnv.override {
      extraLibs = builtins.map (p: interpreter.pkgs.toPythonModule p) plugins;
    };

    # Create a separate environment aggregating the share directory
    # This is done because we only want /share for the actual plugins
    # and not for e.g. the python interpreter and other dependencies.
    manEnv = symlinkJoin {
      name = "${finalDrv.pname}-with-plugins-share-${finalDrv.version}";
      preferLocalBuild = true;
      allowSubstitutes = false;
      paths = plugins;
      postBuild = ''
        if test -e $out/share; then
          mv $out out
          mv out/share $out
        else
          rm -r $out
          mkdir $out
        fi
      '';
    };

  in runCommandNoCC "${finalDrv.pname}-with-plugins-${finalDrv.version}" {
    inherit (finalDrv) passthru meta;
  } ''
    mkdir -p $out/bin

    for bindir in ${lib.concatStringsSep " " (map (d: "${lib.getBin d}/bin") plugins)}; do
      for bin in $bindir/*; do
        ln -s ${buildEnvDrv}/bin/$(basename $bin) $out/bin/
      done
    done

    ln -s ${manEnv} $out/share
  '';

  # Make a python derivation pluginable
  #
  # This adds a `withPlugins` function that works much like `withPackages`
  # except it only links binaries from the explicit derivation /share
  # from any plugins
  toPluginAble = {
    drv
    , interpreter
    , finalDrv
    , self
    , super
  }: drv.overridePythonAttrs(old: {
    passthru = old.passthru // {
      withPlugins = pluginFn: mkPluginDrv {
        plugins = [ finalDrv ] ++ pluginFn self;
        inherit finalDrv;
        inherit interpreter;
      };
    };
  });

  nixops = poetry2nix.mkPoetryApplication {

    projectDir = ./.;

    propagatedBuildInputs = [
      pkgs.openssh
    ];

    nativeBuildInputs = [
      pkgs.docbook5_xsl
      pkgs.libxslt
    ];

    overrides = [
      pkgs.poetry2nix.defaultPoetryOverrides
      overrides
      (self: super: {
        nixops = nixops;
      })
      (self: super: {
        nixops = toPluginAble {
          drv = super.nixops;
          finalDrv = self.nixops;
          interpreter = self.python;
          inherit self super;
        };
      })
    ];

    # TODO: Manual build should be included via pyproject.toml
    postInstall = ''
      cp ${(import ./doc/manual { revision = "1.8"; inherit nixpkgs; }).optionsDocBook} doc/manual/machine-options.xml
      make -C doc/manual install docdir=$out/share/doc/nixops mandir=$out/share/man
    '';

  };

in nixops.python.pkgs.nixops.withPlugins(_: [])
