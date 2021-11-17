# NixOps

[![Test](https://github.com/NixOS/nixops/workflows/CI/badge.svg)](https://github.com/NixOS/nixops/actions)

_NixOps_ is a tool for deploying to [NixOS](https://nixos.org) machines in a network or the cloud. Key features include:

- **Declarative**: NixOps determines and carries out actions necessary to realise a deployment configuration.
- **Testable**: Try your deployments on [VirtualBox](https://github.com/nix-community/nixops-vbox) or [libvirtd](https://github.com/nix-community/nixops-libvirtd).
- **Multi Cloud Support**: Currently supports deployments to [AWS](https://github.com/NixOS/nixops-aws), [Hetzner](https://github.com/NixOS/nixops-hetzner), and [GCE](https://github.com/AmineChikhaoui/nixops-gce)
- **Separation of Concerns**: Deployment descriptions are divided into _logical_ and _physical_ aspects. This makes it easy to separate parts that say _what_ a machine should do from _where_ they should do it.
- **Extensible**: _NixOps_ is extensible through a plugin infrastructure which can be used to provide additional backends.

For more information, please refer to the [NixOps manual](https://nixos.org/nixops/manual/).

### Running

_NixOps_ is included in nixpkgs and can be executed in a shell as follows:

```
$ nix-shell -p nixops
```

or for a bleeding edge version, including many fixes relative to the 1.7 series,

```
$ nix-shell -p nixopsUnstable
```

You may need access to a Nix remote builder if your system does not support the deployment's `system` builds directly. MacOS users may use a virtual machine with NixOS for this purpose.

It is also possible to use cross-compilation with NixOps, by setting `nixpkgs.localSystem` and `nixpkgs.crossSystem`. A mix of remote, emulated and cross builds is also possible; see [this writeup on eno.space](https://eno.space/blog//2021/08/nixos-on-underpowered-devices).

### Building And Developing

#### Building The Nix Package

You can build the Nix package by simply invoking `nix-build` on the project root:

```
$ nix-build
```

#### Development Shell

`shell.nix` provides an environment with all dependencies required for working on _NixOps_. You can use `nix-shell` to
enter a shell suitable for working on _NixOps_ which will contain all Python dependencies specified in [pyproject.toml](./pyproject.toml)

```
$ nix-shell
```

#### Executing Tests

Inside the development shell the tests can be executed as follows:

```
$ ./coverage-tests.py -a '!libvirtd,!gce,!ec2,!azure' -v
```

#### Documentation

NixOps' documentation uses reStructuredText. When editing the docs,
get a live-reloading, rendered version of the docs:

```
nixops$ ./live-docs.py
Serving on http://127.0.0.1:5500
```

and verify its lints before committing:

```
nixops$ lint-docs
```

### Contributing

Contributions to the project are welcome in the form of GitHub PRs. Please consider the following guidelines before creating PRs:

- Please make sure to format your code using [black](https://github.com/psf/black).
- Please add type signatures using [mypy](http://mypy-lang.org/).
- If you are planning to make any considerable changes, you should first present your plans in a GitHub issue so it can be discussed.
- If you are adding features, please also add reasonable tests.

### License

Licensed under [LGPL-3.0](./COPYING).
