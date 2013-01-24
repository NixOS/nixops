#! /bin/sh -e
export NIXOS_CONFIG=/home/eelco/Dev/charon/nix/virtualbox-image-charon.nix
version=$(nix-instantiate --eval-only '<nixos>' -A config.system.nixosVersion | sed s/'"'//g)
echo "version = $version"
nix-build '<nixos>' -A config.system.build.virtualBoxImage
name=virtualbox-charon-$version.vdi.xz
xz < ./result/disk.vdi > $name
scp -p $name root@lucifer:/data/releases/nixos/virtualbox-charon-images/
sha256sum $name
