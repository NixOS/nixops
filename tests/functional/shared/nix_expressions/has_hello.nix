{
  machine = { pkgs, ... }: {
    environment.systemPackages = [ pkgs.hello ];
  };
}
