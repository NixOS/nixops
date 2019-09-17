{ pkgs }: { options, revision }:

let
    options' = pkgs.lib.filter (opt: opt.visible && !opt.internal)
        (pkgs.lib.optionAttrSetToDocList options);

    optionsXML = builtins.toFile "options.xml" (builtins.unsafeDiscardStringContext
        (builtins.toXML options'));
in {
    optionsDocBook = pkgs.runCommand "options-db.xml" {} ''
        ${pkgs.libxslt.bin or pkgs.libxslt}/bin/xsltproc \
        --stringparam revision '${revision}' \
        --stringparam program 'nixops' \
        -o intermediate.xml ${pkgs.path + "/nixos/doc/manual/options-to-docbook.xsl"} ${optionsXML}
        ${pkgs.libxslt.bin or pkgs.libxslt}/bin/xsltproc \
        -o $out ${pkgs.path + "/nixos/doc/manual/postprocess-option-descriptions.xsl"} intermediate.xml
    '';
}