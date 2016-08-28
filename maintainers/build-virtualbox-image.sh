#! /bin/sh -e
export NIXOS_CONFIG=$(readlink -f $(dirname $0)/..)/nix/virtualbox-image-nixops.nix
version=$(nix-instantiate --eval-only '<nixpkgs/nixos>' -A config.system.nixosVersion | sed s/'"'//g)
echo "version = $version"
nix-build '<nixpkgs/nixos>' -A config.system.build.virtualBoxOVA
mkdir ova && tar -xf ./result/*.ova -C ova && mv ova/{nixos*,nixos}.vmdk
name=virtualbox-nixops-$version.vmdk.xz
xz < ./ova/nixos.vmdk > $name
rm -fr ova
scp -p $name hydra-mirror@nixos.org:/data/releases/nixos/virtualbox-nixops-images/
sha256sum $name
