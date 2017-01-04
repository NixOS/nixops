#! /bin/sh -e
export NIXOS_CONFIG=$(readlink -f $(dirname $0)/..)/nix/virtualbox-image-nixops.nix
version=$(nix-instantiate --eval-only '<nixpkgs/nixos>' -A config.system.nixosVersion | sed s/'"'//g)
echo "version = $version"
nix-build '<nixpkgs/nixos>' -A config.system.build.virtualBoxOVA --keep-going --fallback
mkdir ova && tar -xf ./result/*.ova -C ova && mv ova/{nixos*,nixos}.vmdk
name=virtualbox-nixops-$version.vmdk.xz
xz < ./ova/nixos.vmdk > $name
rm -fr ova
aws s3 cp $name s3://nix-releases/nixos/virtualbox-nixops-images/$name
sha256sum $name
