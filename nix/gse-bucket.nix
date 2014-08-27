{ config, pkgs, uuid, name, ... }:

with pkgs.lib;
with (import ./lib.nix pkgs);

let

  corsOptions = { config, ... }: {
    options = {

      maxAgeSeconds = mkOption {
        default = 3600;
        example = 360;
        type = types.nullOr types.int;
        description = ''
          The value, in seconds, to return in the Access-Control-Max-Age
          header used in preflight responses.
        '';
      };

      methods = mkOption {
        default = [ ];
        example = [ "GET" "POST" ];
        type = types.listOf types.str;
        description = ''
          The list of HTTP methods on which to include CORS response headers,
          (GET, OPTIONS, POST, etc). Note: "*" is permitted in the list,
          and means "any method".
        '';
      };

      origins = mkOption {
        default = [ ];
        example = [ "http://example.org" ];
        type = types.listOf types.str;
        description = ''
          The list of Origins eligible to receive CORS response headers.
          Note: "*" is permitted in the list, and means "any Origin".
        '';
      };

      responseHeaders = mkOption {
        default = [ ];
        example = [ "FIXME" ];
        type = types.listOf types.str;
        description = ''
          The list of HTTP headers other than the
          <link xlink:href="http://www.w3.org/TR/cors/#simple-response-header">simple response headers</link>
          to give permission for the user-agent to share across domains.
        '';
      };

    };
    config = {};
  };

  lifecycleOptions = { config, ... }: {
    options = {

      action = mkOption {
        default = "Delete";
        type = types.str;
        description = ''
          The action to perform when all conditions are met.
          Currently only "Delete" is supported by GCE.
        '';
      };

      conditions.age = mkOption {
        default = null;
        example = 365;
        type = types.nullOr types.int;
        description = ''
          This condition is satisfied when an object reaches the specified age (in days).
        '';
      };

      conditions.createdBefore = mkOption {
        default = null;
        example = "2013-01-10";
        type = types.nullOr types.str;
        description = ''
          This condition is satisfied when an object is created
          before midnight of the specified date in UTC.
        '';
      };

      conditions.numberOfNewerVersions = mkOption {
        default = null;
        example = 3;
        type = types.nullOr types.int;
        description = ''
          Relevant only for versioned objects. If the value is N,
          this condition is satisfied when there are at least N versions
          (including the live version) newer than this version of the object.
          For live objects, the number of newer versions is considered to be 0.
          For the most recent archived version, the number of newer versions
          is 1 (or 0 if there is no live object), and so on.
        '';
      };

      conditions.isLive = mkOption {
        default = null;
        type = types.nullOr types.bool;
        description = ''
          Relevant only for versioned objects. If the value is true,
          this condition matches the live objects; if the value is false,
          it matches archived objects.
        '';
      };

    };
    config = {};
  };

in
{

  options = (import ./gce-credentials.nix pkgs "bucket") // {

    name = mkOption {
      example = "my-bucket";
      default = "n-${shorten_uuid uuid}-${name}";
      type = types.str;
      description = "This is the <literal>Name</literal> tag of the bucket.";
    };

    cors = mkOption {
      example = [ {
        maxAgeSeconds = 100;
        methods = [ "GET" "PUT" ];
        origins = [ "http://site.com" "http://site.org" ];
        responseHeaders = [ "header1"  "header2" ];
      } ];
      default = [];
      type = types.listOf types.optionSet;
      options = corsOptions;
      description = ''
        <link xlink:href="http://www.w3.org/TR/cors/">Cross-Origin Resource Sharing</link>
        configuration.
      '';
    };

    lifecycle = mkOption {
      example = [ { conditions.age = 40; } ];
      default = [];
      type = types.listOf types.optionSet;
      options = lifecycleOptions;
      description = ''
        Object Lifecycle Configuration for the bucket contents.
      '';
    };

    logging.logBucket = mkOption {
      default = null;
      example = "resources.gseBuckets.logBucket";
      type = types.nullOr ( types.either types.str (resource "gse-bucket") );
      description = ''
        The destination bucket where the current bucket's logs should be placed.

        FIXME: is this a bucket name or a fully-qualified url?
      '';
    };

    logging.logObjectPrefix = mkOption {
      example = "log";
      default = null;
      type = types.nullOr types.str;
      description = "A prefix for log object names.";
    };

    location = mkOption {
      example = "EU";
      default = "US";
      type = types.str;
      description = ''
        Object data for objects in the bucket resides in physical storage
        within this region. Defaults to US. See the developer's guide for
        the authoritative list.
      '';
    };

    storageClass = mkOption {
      example = "DURABLE_REDUCED_AVAILABILITY";
      default = "STANDARD";
      type = types.str;
      description = ''
        This defines how objects in the bucket are stored and determines
        the SLA and the cost of storage. Typical values are STANDARD and
        DURABLE_REDUCED_AVAILABILITY.
        See the developer's guide for the authoritative list.
      '';
    };

    versioning.enabled = mkOption {
      default = false;
      type = types.bool;
      description = ''
        While set to true, versioning is fully enabled for this bucket.
      '';
    };

    website.mainPageSuffix = mkOption {
      example = "index.html";
      default = null;
      type = types.nullOr types.str;
      description = ''
        Behaves as the bucket's directory index where missing
        objects are treated as potential directories.

        For example, with mainPageSuffix main_page_suffix configured to be index.html,
        a GET request for http://example.com would retrieve http://example.com/index.html,
        and a GET request for http://example.com/photos would
        retrieve http://example.com/photos/index.html.
      '';
    };

    website.notFoundPage = mkOption {
      example = "404.html";
      default = null;
      type = types.nullOr types.str;
      description = ''
        Serve this object on request for a non-existent object.
      '';
    };

  };

  config._type = "gse-bucket";

}
