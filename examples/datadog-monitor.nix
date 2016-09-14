{
  resources.datadogMonitors.bytes_rcvd_monitor = { config, ...}:
    {
      app_key = "...";
      api_key = "...";
      type = "metric alert";
      message = "notify the user @user@example.com";
      renotify_interval = 20;
      include_tags = true;
      no_data_timeframe = 10;
      notify_audit= false;
      query = "avg(last_5m):sum:system.net.bytes_rcvd{host:${config.deployment.name}.machine} > 100";
      thresholds.ok = 10;
      thresholds.warning = 50;
      thresholds.critical = 100;
    };
}