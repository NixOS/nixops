{ pkgs ? import <nixpkgs> {} }:

let
  inherit (pkgs) lib;

  # Embed a default signing policy to work around https://github.com/containers/libpod/issues/6053
  overridePodman = drv: drv.overrideAttrs(old: let
    defaultPolicyFile = pkgs.runCommand "skopeo-default-policy.json" {} "cp ${pkgs.skopeo.src}/default-policy.json $out";    vendorPath = "${old.goPackagePath}/vendor/github.com/containers/image/v5";
  in rec {
    postPatch = ''
      for f in $(grep -lri /etc/containers/policy.json); do
         sed -i -e "s#/etc/containers/policy.json#${defaultPolicyFile}#g" "$f"
       done
    '';
  });

  # Nixpkgs backwards compat, this list should only contain podman
  podmanPkgs =
    if lib.hasAttr "podman-unwrapped" pkgs then
    [ (pkgs.podman.override { podman-unwrapped = (overridePodman pkgs.podman-unwrapped); }) ]
    else [
      (overridePodman pkgs.podman)  # Docker compat
      pkgs.runc  # Container runtime
      pkgs.conmon  # Container runtime monitor
      pkgs.skopeo  # Interact with container registry
      pkgs.slirp4netns  # User-mode networking for unprivileged namespaces
      pkgs.fuse-overlayfs  # CoW for images, much faster than default vfs
    ];

  overrides = import ./overrides.nix { inherit pkgs; };

in pkgs.mkShell {

  buildInputs = [
    (pkgs.poetry2nix.mkPoetryEnv {
      projectDir = ./.;
      overrides = pkgs.poetry2nix.overrides.withDefaults(overrides);
    })
    pkgs.openssh
    pkgs.poetry
  ] ++ podmanPkgs;

  shellHook = ''
    export PATH=${builtins.toString ./scripts}:$PATH
  '';

}
