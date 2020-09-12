{ module, revision ? "local", nixpkgs ? <nixpkgs> }:

let

  pkgs = import nixpkgs {};

  systemModule = pkgs.lib.fixMergeModules [ module ]
    { inherit pkgs; utils = {}; name = "<name>"; uuid = "<uuid>"; };

  options = pkgs.lib.filter (opt: opt.visible && !opt.internal) (pkgs.lib.optionAttrSetToDocList systemModule.options);

  optionsXML = builtins.toFile "options.xml" (builtins.unsafeDiscardStringContext
    (builtins.toXML options));

  optionsDocBook = pkgs.runCommand "options-db.xml" {} ''
    ${pkgs.libxslt.bin or pkgs.libxslt}/bin/xsltproc \
      --stringparam revision '${revision}' \
      -o intermediate.xml ${nixpkgs + /nixos/lib/make-options-doc/options-to-docbook.xsl} ${optionsXML}
      ${pkgs.libxslt.bin or pkgs.libxslt}/bin/xsltproc \
      -o $out ${nixpkgs + /nixos/lib/make-options-doc/postprocess-option-descriptions.xsl} intermediate.xml
  '';

in optionsDocBook
