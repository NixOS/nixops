let
  app_key = "ec0...";
  api_key = "1b4...";
in
{
  resources.datadogScreenboards.screenboard-example = { config, ...}:
  {
    appKey = app_key;
    apiKey = api_key;
    boardTitle = "Screenboard created using nixops";
    description = "Screenboard created using NixOps";
    templateVariables = [
      {
        name = "host";
        prefix = "host";
        default = "*";
      }
    ];
    widgets = [
      (builtins.toJSON {
        legend= false;
        type= "timeseries";
        legend_size= "0";
        x= 0;
        y= 0;
        timeframe= "1h";
        title_size= 16;
        title= true;
        title_align= "left";
        title_text= "CPU iowait";
        height= 13;
        tile_def= {
          requests= [
            {
              type= "line";
              conditional_formats= [];
              q= "sum:system.cpu.iowait{$host}";
            }
          ];
          viz= "timeseries";
        };
        width= 54;
      })
    ];
  };
}
