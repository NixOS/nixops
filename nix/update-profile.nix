{ machines }:

with import <nixpkgs> {};
with lib;

runCommand "nixops-machines" {}
  ''
    mkdir -p $out
    ${concatStrings (mapAttrsToList (n: v: ''
      ln -s "${v}" $out/"${n}"
    '') machines)}
  ''
