Authoring a Plugin
==================

NixOps plugins extend NixOps core to support additional hosting
providers and resource types.

Some example plugins include:

- https://github.com/NixOS/nixops-aws
- https://github.com/NixOS/nixops-hetzner
- https://github.com/nix-community/nixops-vbox
- https://github.com/nix-community/nixops-libvirtd
- https://github.com/nix-community/nixops-datadog

This guide is light on the details, and intends to describe just the
supported hooks and integration process.

Packaging with Poetry and poetry2nix
------------------------------------

NixOps and its plugins are packaged as standard Python applications.
Most packages will use `Poetry <https://python-poetry.org>`_ and
`poetry2nix <https://github.com/nix-community/poetry2nix>`_ for
packaging with Nix.

Note: NixOps is formatted with ``black`` and strictly typechecked with
``mypy``. Your project should follow these guidelines as well, and use
a mypy configuration at least as strict as the NixOps mypy
configuration.

First, create a ``pyproject.toml`` (see `PEP-0517
<https://www.python.org/dev/peps/pep-0517/>`_ to describe your
project. We do not use setup.py, and trying to use both a ``setup.py``
and ``pyproject.toml`` may cause confusing build errors. Only use a
``pyproject.toml``:

.. code-block:: toml

  [tool.poetry]
  name = "nixops_neatcloud"
  version = "1.0"
  description = "NixOps plugin for NeatCloud"
  authors = ["Your Name <your.name@example.com>"]
  license = "MIT"
  include = [ "nixops_neatcloud/nix/*.nix" ]

  [tool.poetry.dependencies]
  python = "^3.7"
  nixops = {git = "https://github.com/NixOS/nixops.git", rev = "master"}

  [tool.poetry.dev-dependencies]
  mypy = "^0.770"
  black = "^19.10b0"

  [tool.poetry.plugins."nixops"]
  neatcloud = "nixops_neatcloud.plugin"

  [build-system]
  requires = ["poetry>=0.12"]
  build-backend = "poetry.masonry.api"

Important Notes
***************

1. If you have a ``setup.py``, delete it now.
2. If your plugin is named ``nixops_neatcloud``, the source directory
   must be named ``nixops_neatcloud``.
3. If your source directory was named ``nixopsneatcloud``, please
   rename it to ``nixops_neatcloud``.
4. Older style plugins used to store the Nix expressions in a directory
   named ``nix`` next to the python plugin directory, like this::

     .
     ├── nix
     │   └── default.nix
     └── nixops_neatcloud
         ├── __init__.py
         └── plugin.py

   plugins must now put the nix expressions underneat the plugin's
   python directory::

     .
     └── nixops_neatcloud
         ├── nix
         │   └── default.nix
         ├── __init__.py
         └── plugin.py

   and the nixexprs hook function which looked like this:

   .. code-block:: python

     @nixops.plugins.hookimpl
     def nixexprs():
         expr_path = os.path.realpath(os.path.dirname(__file__) + "/../../../../share/nix/nixops-vbox")
         if not os.path.exists(expr_path):
             expr_path = os.path.realpath(os.path.dirname(__file__) + "/../../../../../share/nix/nixops-vbox")
         if not os.path.exists(expr_path):
             expr_path = os.path.dirname(__file__) + "/../nix"

         return [
             expr_path
         ]

   can now look like this:

   .. code-block:: python

     @nixops.plugins.hookimpl
     def nixexprs():
         return [
             os.path.dirname(os.path.abspath(__file__)) + "/nix"
         ]

5. Resource subclasses must now work with Python objects instead of XML

   This old-style ResourceDefinition subclass:

   .. code-block:: python

     class NeatCloudMachineDefinition(nixops.resources.ResourceDefinition):

         def __init__(self, xml):
             super().__init__(xml)
             self.store_keys_on_machine = (
                 xml.find("attrs/attr[@name='storeKeysOnMachine']/bool").get("value")
                 == "true"
             )

   Should now look like:

   .. code-block:: python

     class NeatCloudMachineOptions(nixops.resources.ResourceOptions):
         storeKeysOnMachine: bool

     class NeatCloudMachineDefinition(nixops.resources.ResourceDefinition):

         config: MachineOptions

         store_keys_on_machine: bool

         def __init__(self, name: str, config: nixops.resources.ResourceEval):
             super().__init__(name, config)
             self.store_keys_on_machine = config.storeKeysOnMachine

   ``ResourceEval`` is an immutable ``typing.Mapping`` implementation.
   Also note that ``ResourceEval`` has turned Nix lists into Python tuples, dictionaries into ResourceEval objects and so on.
   ``typing.Tuple`` cannot be used as it's fixed-size, use ``typing.Sequence`` instead.

   ``ResourceOptions`` is an immutable object that provides type validation both with ``mypy`` _and_ at runtime.
   Any attributes which are not explicitly typed are passed through as-is.


On with Poetry
**************

Now create your first ``poetry.lock`` file with ``poetry lock``::

  nixops_neatcloud$ nix-shell -p poetry
  [nix-shell:nixops_neatcloud]$ poetry lock
  Creating virtualenv nixops_neatcloud-FrXThxiS-py3.7 in ~/.cache/pypoetry/virtualenvs
  Updating dependencies
  Resolving dependencies... (2.1s)

  Writing lock file

Exit the Nix shell, and create the supporting Nix files.

Create a ``default.nix``:

.. code-block:: nix

  { pkgs ? import <nixpkgs> {} }:
  let
    overrides = import ./overrides.nix { inherit pkgs; };
  in pkgs.poetry2nix.mkPoetryApplication {
    projectDir = ./.;
    overrides = pkgs.poetry2nix.overrides.withDefaults overrides;
  }

And a minimal ``overrides.nix``:

.. code-block:: nix

  { pkgs }:

  self: super: {
    nixops = super.nixops.overridePythonAttrs({ nativeBuildInputs ? [], ... }: {
      format = "pyproject";
      nativeBuildInputs = nativeBuildInputs ++ [ self.poetry ];
    });
  }

and finally, a ``shell.nix``:

.. code-block:: nix

  { pkgs ? import <nixpkgs> {} }:
  let
    overrides = import ./overrides.nix { inherit pkgs; };
  in pkgs.mkShell {
    buildInputs = [
      (pkgs.poetry2nix.mkPoetryEnv {
        projectDir = ./.;
        overrides = pkgs.poetry2nix.overrides.withDefaults overrides;
      })
      pkgs.poetry
    ];
  }

Now you can enter a Nix and Poetry shell to develop on your plugin::

  nixops_neatcloud$ nix-shell
  [nix-shell:nixops_neatcloud]$ poetry install
  [nix-shell:nixops_neatcloud]$ poetry shell

Note: ``install`` is making a virtual environment, and does not
install anything in the traditional sense.

Create an empty file at ``nixops_neatcloud/plugin.py``, and then
you'll be able to list plugins and see your plugin:

Now you can list plugins and see your plugin is installed::

  (nixops_neatcloud-FrXThxiS-py3.7)
  nixops_neatcloud$ nixops list-plugins
  +-------------------+
  | Installed Plugins |
  +-------------------+
  |     neatcloud     |
  +-------------------+

At this point, you can develop your plugin from within this shell,
running ``nixops`` and ``mypy nixops_neatcloud``./

Plug-in Loading
---------------

NixOps uses `Pluggy <https://pluggy.readthedocs.io/en/latest/>`_ to
discover and load plugins. The glue which hooks things together is in
``pyproject.toml``:

.. code-block:: toml

  [tool.poetry.plugins."nixops"]
  neatcloud = "nixops_neatcloud.plugin"

NixOps implements a handful of hooks which your plugin can integrate
with. See ``nixops/plugins/hookspec.py`` for a complete list.

Developing NixOps and a plugin at the same time
-----------------------------------------------

In this case you want a mutable copy of NixOps and your plugin. Since
we are developing the plugin like any other Python program, we can
specify a relative path to NixOps's source in the pyproject.toml:

.. code-block:: toml

  nixops = { path = "../nixops" }

Then run `poetry lock; poetry install; poetry shell` like normal.

Troubleshooting
---------------

If you run in to trouble, you might try deleting some things::

  $ rm -rf nixops_neatcloud.egg-info pip-wheel-metadata/

Building a dependency fails
---------------------------

First, run your ``nix-shell`` or ``nix-build`` with ``--keep-going``
and then again with ``--jobs 1`` to isolate the cause. The first run
will build everything it can complete, and the second one will build
only one derivation and then fail::

  nixops_neatcloud$ nix-shell -j1 --keep-going
  these derivations will be built:
    /nix/store/3s2a0hky73b24m4yppd7581c9w2clpnb-python3.7-nixops-1.8.0.drv
    /nix/store/bv6gwayic2xxx3pd489d4gbs03kafxsd-python3-3.7.6-env.drv
  building '/nix/store/3s2a0hky73b24m4yppd7581c9w2clpnb-python3.7-nixops-1.8.0.drv'...
  [...]
  Traceback (most recent call last):
    File "nix_run_setup", line 8, in <module>
      exec(compile(getattr(tokenize, 'open', open)(__file__).read().replace('\\r\\n', '\\n'), __file__, 'exec'))
    File "/nix/store/n8nviwmllwqv0fjsar8v8k8gjap1vhcw-python3-3.7.6/lib/python3.7/tokenize.py", line 447, in open
      buffer = _builtin_open(filename, 'rb')
  FileNotFoundError: [Errno 2] No such file or directory: 'setup.py'
  builder for '/nix/store/3s2a0hky73b24m4yppd7581c9w2clpnb-python3.7-nixops-1.8.0.drv' failed with exit code 1
  cannot build derivation '/nix/store/bv6gwayic2xxx3pd489d4gbs03kafxsd-python3-3.7.6-env.drv': 1 dependencies couldn't be built
  error: build of '/nix/store/bv6gwayic2xxx3pd489d4gbs03kafxsd-python3-3.7.6-env.drv' failed

If a dependency is missing, add the dependency to your
``pyproject.toml``, and add an override like the Toml example for Zipp.

Zipp can't find toml
********************

Add zipp to your ``overrides.nix``, providing toml explicitly:

.. code-block:: nix

  { pkgs }:

  self: super: {
    zipp = super.zipp.overridePythonAttrs({ propagatedBuildInputs ? [], ... } : {
      propagatedBuildInputs = propagatedBuildInputs ++ [
        self.toml
      ];
    });
  }

FileNotFoundError: [Errno 2] No such file or directory: 'setup.py'
******************************************************************

This dependency needs to be built in the ``pyproject`` format, which
means it will also need poetry as a dependency. Add this to your
``overrides.nix``:

.. code-block:: nix

    package-name = super.package-name.overridePythonAttrs({ nativeBuildInputs ? [], ... }: {
      format = "pyproject";
      nativeBuildInputs = nativeBuildInputs ++ [ self.poetry ];
    });
