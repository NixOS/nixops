{ account
, region ? "us-east-1"
, description ? "CloudWatch example"
, ...
}:
{
  network.description = description;

  resources.cloudwatchLogStreams.stream = {resources,...}: {
    name="nixops-stream";
    accessKeyId = account;
    logGroupName="${resources.cloudwatchLogGroups.log-group.name}";
    inherit region;
  };

  resources.cloudwatchLogGroups.log-group = {
    name="nixops-cloudwatch";
    retentionInDays=30;
    accessKeyId = account;
    inherit region;
  };

}
