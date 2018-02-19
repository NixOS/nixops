{ accessKeyId ? "nixos-tests"
, region ? "us-east-1"
, ...
}:
{
  require = [ ./trivial-ec2.nix ];

  resources.snsTopics.alert-topic = {
    displayName = "SNS alert topic";
    subscriptions = [
    {
      protocol = "email";
      endpoint = "rob.vermaas+alerts@gmail.com";
    }
    ];
    inherit region accessKeyId;
  };

  resources.cloudwatchMetricAlarms.my-alarm =
    { resources, ... }:
    { metricName = "StatusCheckFailed";
      namespace = "AWS/EC2";
      statistic = "Maximum";
      dimensions = [ { Name = "InstanceId"; Value = resources.machines.machine; } ];
      unit = "Count";
      period = 300;
      evaluationPeriods = 2;
      threshold = 1;
      comparisonOperator = "GreaterThanOrEqualToThreshold";
      datapointsToAlarm = 1;
      alarmActions = [ resources.snsTopics.alert-topic ];
      insufficientDataActions = [ resources.snsTopics.alert-topic ];

      inherit region accessKeyId;
    };
}
