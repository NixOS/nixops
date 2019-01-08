{
  resources.datadogMonitors.bytes_rcvd_monitor = { config, ...}:
    {
      appKey = "...";
      apiKey = "...";
      type = "metric alert";
      message = "notify the user @user@example.com";
      query = "avg(last_5m):sum:system.net.bytes_rcvd{host:${config.deployment.name}.machine} > 100";
      monitorTags = ["tag1" "tag2"];
      monitorOptions = builtins.toJSON {
        renotify_interval = 20;
        include_tags = true;
        no_data_timeframe = 10;
        notify_audit= false;
        thresholds.ok = 10;
        thresholds.warning = 50;
        thresholds.critical = 100;
      };
    };
}
