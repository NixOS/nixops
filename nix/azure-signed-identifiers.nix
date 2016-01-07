lib:
with lib;

mkOption {
  default = {};
  type = types.attrsOf types.optionSet;
  example = {
    "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTI=" = {
      start = "2013-11-26T08:49:37.0000000Z";
      expiry = "2013-11-27T08:49:37.0000000Z";
      permissions = "raud";
    };
  };

  description = ''
    An attribute set of Signed Identifiers and the corresponding
    access policies that may be used with Shared Access Signatures.
  '';

  options = { config, ... }: {
    options = {
      start = mkOption {
        example = "2013-11-26T08:49:37.0000000Z";
        type = types.str;
        description = ''
          Access policy start UTC date/time in a valid ISO 8061 format.
          Supported ISO 8061 formats include the following:
          YYYY-MM-DD, YYYY-MM-DDThh:mmTZD, YYYY-MM-DDThh:mm:ssTZD, YYYY-MM-DDThh:mm:ss.ffffffTZD
        '';
      };

      expiry = mkOption {
        example = "2013-11-26T08:49:37.0000000Z";
        type = types.str;
        description = ''
          Access policy expiry UTC date/time in a valid ISO 8061 format.
          Supported ISO 8061 formats include the following:
          YYYY-MM-DD, YYYY-MM-DDThh:mmTZD, YYYY-MM-DDThh:mm:ssTZD, YYYY-MM-DDThh:mm:ss.ffffffTZD
        '';
      };

      permissions = mkOption {
        example = "raud";
        type = types.str;
        description = ''
          Abbreviated permission list.
        '';
      };

    };
    config = {};
  }; 
}
