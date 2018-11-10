{ pkgs, diskImageFun, debianDistro, debianCodename, debianPackages
, extraPackages ? []
}:

let
  # Has to match with the version used in the Debian repository.
  gnupg = pkgs.gnupg20;

  reprepro = pkgs.stdenv.mkDerivation rec {
    name = "reprepro-${version}";
    version = "4.16.0";

    src = pkgs.fetchurl {
      url = "https://alioth.debian.org/frs/download.php/file/"
          + "4109/reprepro_${version}.orig.tar.gz";
      sha256 = "14gmk16k9n04xda4446ydfj8cr5pmzsmm4il8ysf69ivybiwmlpx";
    };

    nativeBuildInputs = [ pkgs.makeWrapper ];
    buildInputs = pkgs.lib.singleton (pkgs.gpgme.override { inherit gnupg; })
               ++ (with pkgs; [ db libarchive bzip2 xz zlib ]);

    postInstall = ''
      wrapProgram "$out/bin/reprepro" --prefix PATH : "${gnupg}/bin"
    '';
  };

  repoKeys = pkgs.vmTools.runInLinuxVM (pkgs.stdenv.mkDerivation {
    name = "snakeoil-repository-keys";

    outputs = [ "out" "publicKey" "publicKeyId" "secretKeyId" ];

    buildCommand = ''
      export GNUPGHOME="$out"
      mkdir -p "$GNUPGHOME"
      rm -f /dev/random
      ln -s urandom /dev/random
      mknod /dev/console c 5 1

      cat > template <<EOF
      %echo Generating a repository signing key
      %transient-key
      %no-protection
      Key-Type: DSA
      Key-Usage: sign
      Name-Real: Snake Oil
      Name-Email: snake@oil
      Expire-Date: 0
      %commit
      %echo Repository key created
      EOF

      ${gnupg}/bin/gpg2 --batch --gen-key template

      ${gnupg}/bin/gpg2 --list-secret-keys --with-colons | \
        grep '^sec:' | cut -d: -f5 > "$secretKeyId"
      ${gnupg}/bin/gpg2 --list-public-keys --with-colons | \
        grep '^pub:' | cut -d: -f5 > "$publicKeyId"
      ${gnupg}/bin/gpg2 --export \
        "$(< "$publicKeyId")" \
        > "$publicKey"
    '';
  });

  keyringPackage = pkgs.vmTools.runInLinuxImage (pkgs.stdenv.mkDerivation {
    name = "snakeoil-archive-keyring.deb";

    diskImage = diskImageFun {
      extraPackages = [ "build-essential" "gnupg" "apt" "debhelper" ];
    };

    GNUPGHOME = repoKeys;

    buildCommand = ''
      mkdir snakeoil-archive-keyring
      cd snakeoil-archive-keyring
      cat "${repoKeys.publicKey}" > snakeoil-archive-keyring.gpg
      mkdir -p debian/source
      echo 9 > debian/compat
      echo '3.0 (native)' > debian/source/format
      cp "${pkgs.writeText "install" ''
        snakeoil-archive-keyring.gpg /usr/share/keyrings
        snakeoil-archive-keyring.gpg /etc/apt/trusted.gpg.d
      ''}" debian/install
      cp "${pkgs.writeScript "rules" ''
        #!/usr/bin/make -f
        %:
        ${"\t"}dh $@
      ''}" debian/rules
      cp "${pkgs.writeText "changelog" ''
        snakeoil-archive-keyring (1-1) unstable; urgency=low

          * Dummy changelog for snakeoil key.

         -- Snake Oil <snake@oil>  Thu, 01 Jan 1970 00:00:01 +0000
      ''}" debian/changelog
      cp "${pkgs.writeText "control" ''
        Source: snakeoil-archive-keyring
        Section: misc
        Priority: optional
        Maintainer: Snake Oil <snake@oil>
        Build-Depends: debhelper (>= 9), gnupg, apt
        Standards-Version: 3.9.6

        Package: snakeoil-archive-keyring
        Architecture: all
        Depends: ''${misc:Depends}
        Description: Snakeoil archive signing key
      ''}" debian/control
      dpkg-buildpackage -b
      rmdir "$out" || :
      mv -vT ../*.deb "$out" # */
    '';
  });

  repository = pkgs.stdenv.mkDerivation {
    name = "apt-repository";

    toInclude = let
      expr = pkgs.vmTools.debClosureGenerator {
        packages = debianDistro.packages ++ debianPackages;
        inherit (debianDistro) name urlPrefix;
        packagesLists = [ debianDistro.packagesList ];
      };
    in import expr {
      inherit (pkgs) fetchurl;
    };

    GNUPGHOME = repoKeys;

    buildCommand = ''
      mkdir -p "$out"/{conf,dists,incoming,indices,logs,pool,project,tmp}
      cat > "$out/conf/distributions" <<RELEASE
      Origin: Debian
      Label: Debian
      Codename: ${debianCodename}
      Architectures: amd64
      Components: main
      Description: Debian package cache
      SignWith: $(< "${repoKeys.secretKeyId}")
      RELEASE

      # Create APT repository
      printf "Creating APT repository..." >&2
      for debfile in $toInclude ${keyringPackage} ${toString extraPackages}; do
        REPREPRO_BASE_DIR="$out" ${reprepro}/bin/reprepro includedeb \
          "${debianCodename}" "$debfile" > /dev/null
      done
      echo " done." >&2
    '';

    passthru.serve = pkgs.writeScript "serve-debian-repo" ''
      #!${pkgs.stdenv.shell}
      exec ${pkgs.thttpd}/sbin/thttpd -d "${repository}" \
                                      -l /dev/null \
                                      -i "$(pwd)/repo.pid"
    '';

    passthru.publicKey = repoKeys.publicKey;
  };

in repository
