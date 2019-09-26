# NixOps

NixOps (formerly known as Charon) is a tool for deploying NixOS
machines in a network or cloud.

* [Manual](https://nixos.org/nixops/manual/)
* [Installation](https://nixos.org/nixops/manual/#chap-installation) / [Hacking](https://nixos.org/nixops/manual/#chap-hacking)
* [Continuous build](http://hydra.nixos.org/jobset/nixops/master#tabs-jobs)
* [Source code](https://github.com/NixOS/nixops)
* [Issue Tracker](https://github.com/NixOS/nixops/issues)
* [Mailing list / Google group](https://groups.google.com/forum/#!forum/nixops-users)
* [IRC - #nixos on freenode.net](irc://irc.freenode.net/#nixos)

## Developing

To start developing on nixops, you can run:

```bash
  $ nix dev-shell
```

## Building from source

The command to build NixOps depends on your platform and which plugins you choose:

- `nix build .#hydraJobs.build.x86_64-linux` on 64 bit linux.
- `nix-build .#hydraJobs.build.i686-linux` on 32 bit linux.
- `nix-build .#hydraJobs.build.x86_64-darwin` on OSX.

NixOps can be imported into another flake as follows:

```nix
{
  edition = 201909;

  inputs.nixops.uri = github:NixOS/nixops;

  outputs = { self, nixpkgs, nixops }: {
    packages.my-package =
      let
        pkgs = import nixpkgs {
          system = "x86_linux";
          overlays = [ nixops.overlay ];
        };
      in
        pkgs.stdenv.mkDerivation {
          ...
          buildInputs = [ pkgs.nixops ];
        };
  };
}
```
