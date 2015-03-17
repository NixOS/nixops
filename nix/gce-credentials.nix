lib: name:
with lib;
{

  serviceAccount = mkOption {
    default = "";
    example = "12345-asdf@developer.gserviceaccount.com";
    type = types.str;
    description = ''
      The GCE Service Account Email. If left empty, it defaults to the
      contents of the environment variable <envar>GCE_SERVICE_ACCOUNT</envar>.
    '';
  };

  accessKey = mkOption {
    default = "";
    example = "/path/to/secret/key.pem";
    type = types.str;
    description = ''
      The path to GCE Service Account key. If left empty, it defaults to the
      contents of the environment variable <envar>ACCESS_KEY_PATH</envar>.
    '';
  };

  project = mkOption {
    default = "";
    example = "myproject";
    type = types.str;
    description = ''
      The GCE project which should own the ${name}. If left empty, it defaults to the
      contents of the environment variable <envar>GCE_PROJECT</envar>.
    '';
  };

}
