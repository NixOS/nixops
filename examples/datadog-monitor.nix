{
  resources.datadogMonitors.bytes_rcvd_monitor = { config, ...}:
    {
      appKey = "...";
      apiKey = "...";
      type = "metric alert";
      message = "notify the user @user@example.com";
      renotifyInterval = 20;
      includeTags = true;
      noDataTimeframe = 10;
      notifyAudit= false;
      query = "avg(last_5m):sum:system.net.bytes_rcvd{host:${config.deployment.name}.machine} > 100";
      thresholds.ok = 10;
      thresholds.warning = 50;
      thresholds.critical = 100;
    };
}