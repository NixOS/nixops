# NixOps

NixOps (formerly known as Charon) is a tool for deploying NixOS
machines in a network or cloud.

* [Manual](https://hydra.nixos.org/job/nixops/master/tarball/latest/download-by-type/doc/manual)
* [Installation](https://nixos.org/nixops/manual/#chap-installation) / [Hacking](https://hydra.nixos.org/job/nixops/master/tarball/latest/download-by-type/doc/manual#chap-hacking)
* [Continuous build](http://hydra.nixos.org/jobset/nixops/master#tabs-jobs)
* [Issue Tracker](https://github.com/NixOS/nixops/issues)
* [Mailing list / Google group](https://groups.google.com/forum/#!forum/nixops-users)
* [IRC - #nixos on freenode.net](irc://irc.freenode.net/#nixos)

## Developing

To start developing on nixops, you can run:

```bash
  $ ./dev-shell
```

## Building from source

The command to build NixOps depends on your platform you choose:

- `nix-build release.nix -A build.x86_64-linux on 64 bit linux.
- `nix-build release.nix -A build.i686-linux on 32 bit linux.
- `nix-build release.nix -A build.x86_64-darwin on OSX.

Similarly, using NixOps from another project (for instance a nix-shell) can be done using:

```nix
stdenv.mkDerivation {
  name = "my-nixops-env";
  buildInputs = [
    (import /path/to/nixops/release.nix { }).nixops.x86_64-linux
  ];
}
```
