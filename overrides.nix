{ pkgs }:

self: super: {
  zipp = super.zipp.overridePythonAttrs(old: {
    propagatedBuildInputs = old.propagatedBuildInputs ++ [
      self.toml
    ];
  });
}
