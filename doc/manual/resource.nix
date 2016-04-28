{ module, revision ? "local" }:

let

  pkgs = import <nixpkgs> {};

  systemModule = pkgs.lib.fixMergeModules [ module ]
    { inherit pkgs; utils = {}; name = "<name>"; uuid = "<uuid>"; };

  optionsXML = builtins.toFile "options.xml" (builtins.unsafeDiscardStringContext
    (builtins.toXML (pkgs.lib.optionAttrSetToDocList systemModule.options)));

  optionsDocBook = pkgs.runCommand "options-db.xml" {} ''
    ${pkgs.libxslt.bin or pkgs.libxslt}/bin/xsltproc \
      --stringparam revision '${revision}' \
      -o $out ${<nixpkgs/nixos/doc/manual/options-to-docbook.xsl>} ${optionsXML}
  '';

in optionsDocBook
