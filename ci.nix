{ lib ? import <nixpkgs/lib>
, pkgs ? import <nixpkgs> {}
}:
with builtins; with lib;
let
  ciPath = "./.github/workflows/ci.yml";
  checkout = {
    name = "Checkout";
    uses = "actions/checkout@v2";
  };
  nix = {
    name = "Nix";
    uses = "cachix/install-nix-action@v7";
  };
  mkJob = extraSteps: {
    runs-on = "ubuntu-latest";
    steps = [ checkout nix ] ++ extraSteps;
  };
  ci = {
    on.push.branches = [ "*" ];
    name = "CI";
    jobs = {
      parsing = mkJob [{
          name = "Parsing";
          run = "find . -name \"*.nix\" -exec nix-instantiate --parse --quiet {} >/dev/null +";
      }];
      mypy = mkJob [{
        name = "MyPy";
        run = "nix-shell --run \"mypy nixops\"";
      }];
      black = mkJob [{
        name = "Black";
        run = "nix-shell --run \"black . --check --diff\"";
      }];
      coverage = mkJob [{
        name = "Coverage";
        run = "nix-shell --exclude tarball --run \"./coverage-tests.py -a '!libvirtd,!gce,!ec2,!azure' -v\"";
      }];
      build = mkJob [{
        name = "Build";
        run = "nix-build --quiet release.nix -A build.x86_64-linux -I nixpkgs=channel:19.09";
      }];
      ciCheck = mkJob [{
        name = "Check CI";
        run = ''
          cp ${ciPath} /tmp/ci.reference.yml
          nix-build ci.nix --no-out-link | bash
          diff ${ciPath} /tmp/ci.reference.yml || exit 1
        '';
      }];
    };
  };
  generated = pkgs.writeText "ci.yml" (builtins.toJSON ci);
in
  pkgs.writeShellScript "gen_ci" ''
    mkdir -p "$(dirname ${ciPath})"
    cat ${generated} > ${ciPath}
''
