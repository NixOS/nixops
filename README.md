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
  $ ./dev-shell --arg p "(p: [ p.plugin1 ])"
```

Where plugin1 can be any available nixops plugin, and where
none or more than one can be specified, including local plugins.  An example is:


```bash
  $ ./dev-shell --arg p "(p: [ p.aws p.packet (p.callPackage ../myplugin/release.nix {})])"
```

To update the available nixops plugins, edit the
all-plugins.txt file with any new plugin repos and
then execute the update-all script.  This will refresh
the data.nix file.

## Building from source

The command to build NixOps depends on your platform and which plugins you choose:

- `nix-build release.nix -A build.x86_64-linux --arg p "(p: [ p.plugin1 ])"` on 64 bit linux.
- `nix-build release.nix -A build.i686-linux --arg p "(p: [ p.plugin1 ])"` on 32 bit linux.
- `nix-build release.nix -A build.x86_64-darwin --arg p "(p: [ p.plugin1 ])"` on OSX.

Similarly, using NixOps from another project (for instance a nix-shell) can be done using:

```nix
stdenv.mkDerivation {
  name = "my-nixops-env";
  buildInputs = [
    (import /path/to/nixops/release.nix { p = (p: [ p.plugin1 ]); }).build.x86_64-linux
  ];
}
```
