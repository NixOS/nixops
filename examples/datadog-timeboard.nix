let
  app_key = "ec0d...";
  api_key = "1b4...";
in
{
  resources.datadogTimeboards.test-timeboard = { config, ...}:
  {
    appKey = app_key;
    apiKey = api_key;
    title = "Timeboard created using NixOps";
    description = "Timeboard created using NixOps";
    templateVariables = [
      {
        name = "host";
        prefix = "host";
        default = "*";
      }
    ];
    graphs = [
      {
        title = "system.disk.free, system.disk.used";
        definition = builtins.toJSON {
          requests= [
            {
              type= "line";
              conditional_formats= [];
              aggregator= "avg";
              q= "avg:system.disk.free{device:/dev/dm-0,host:i-494dad79}";
            }
            {
              type= "line";
              conditional_formats= [];
              aggregator= "avg";
              q= "avg:system.disk.used{device:/dev/dm-0,host:i-494dad79}";
            }
          ];
          viz= "timeseries";
        };
      }
    ];
  };
}
