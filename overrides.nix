{ pkgs }:

self: super: {
  zipp = super.zipp.overridePythonAttrs(old: {
    propagatedBuildInputs = old.propagatedBuildInputs ++ [
      self.toml
    ];
  });
  sphinx = super.sphinx.overridePythonAttrs (old: {
    buildInputs = (old.buildInputs or [ ]) ++ [
      self.flit-core
    ];
  });
}
