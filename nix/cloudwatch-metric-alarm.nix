{ config, lib, uuid, name, ... }:

with lib;
with (import ./lib.nix lib);

{

  options = {
    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the CloudWatch Metric Alarm.";
    };

    accessKeyId = mkOption {
      type = types.str;
      default = "";
      description = ''
        The AWS Access Key ID.  If left empty, it defaults to the
        contents of the environment variables
        <envar>EC2_ACCESS_KEY</envar> or
        <envar>AWS_ACCESS_KEY_ID</envar> (in that order).  The
        corresponding Secret Access Key is not specified in the
        deployment model, but looked up in the file
        <filename>~/.ec2-keys</filename>, which should specify, on
        each line, an Access Key ID followed by the corresponding
        Secret Access Key. If the lookup was unsuccessful it is continued
        in the standard AWS tools <filename>~/.aws/credentials</filename> file.
        If it does not appear in these files, the
        environment variables
        <envar>EC2_SECRET_KEY</envar> or
        <envar>AWS_SECRET_ACCESS_KEY</envar> are used.
      '';
    };

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    metricName = mkOption {
      type = types.str;
      description = ''
        The name of the metric associated with the alarm.
      '';
    };

    namespace = mkOption {
      type = types.str;
      description = ''
        The namespace of the metric associated with the alarm.
      '';
    };

    statistic = mkOption {
      type = types.enum [ "SampleCount" "Average" "Sum" "Minimum" "Maximum" ];
      description = ''
        The statistic for the metric associated with the alarm, other than percentile.
      '';
    };

    dimensions = mkOption {
      default = [];
      type = types.listOf (types.submodule {
        options = {
          Name = mkOption {
            type = types.str;
            description = ''
              The name of the dimension.
            '';
          };
          Value = mkOption {
            type = types.either types.str (resource "machine");
            apply = x: if builtins.isString x then x else "machine-" + x._name;
            description = ''
              The value representing the dimension measurement.
            '';
          };
        };
      });
      description = ''
        The dimensions for the metric associated with the alarm.
      '';
    };

    unit = mkOption {
      type = types.enum [
        "Seconds"
        "Microseconds"
        "Milliseconds"
        "Bytes"
        "Kilobytes"
        "Megabytes"
        "Gigabytes"
        "Terabytes"
        "Bits"
        "Kilobits"
        "Megabits"
        "Gigabits"
        "Terabits"
        "Percent"
        "Count"
        "Bytes/Second"
        "Kilobytes/Second"
        "Megabytes/Second"
        "Gigabytes/Second"
        "Terabytes/Second"
        "Bits/Second"
        "Kilobits/Second"
        "Megabits/Second"
        "Gigabits/Second"
        "Terabits/Second"
        "Count/Second"
        "None"
      ];
      description = ''
        The unit of the metric associated with the alarm.
      '';
    };

    period = mkOption {
      type = types.int;
      description = ''
        The period, in seconds, over which the statistic is applied.
      '';
    };

    evaluationPeriods = mkOption {
      type = types.int;
      description = ''
        The number of periods over which data is compared to the specified threshold.
      '';
    };

    threshold = mkOption {
      type = types.int;
      description = ''
        The value to compare with the specified statistic.
      '';
    };

    comparisonOperator = mkOption {
      type = types.enum [ "GreaterThanOrEqualToThreshold" "GreaterThanThreshold" "LessThanThreshold" "LessThanOrEqualToThreshold" ];
      description = ''
        The arithmetic operation to use when comparing the specified statistic and
        threshold. The specified statistic value is used as the first operand.
      '';
    };

    alarmActions = mkOption {
      type = types.listOf (types.either types.str (resource "sns-topic"));
      apply = map (x: if builtins.isString x then x else "res-" + x._name);
      default = [];
      description = ''
        The actions to execute when this alarm transitions to the ALARM state from
        any other state. 
      '';
    };

    okActions = mkOption {
      type = types.listOf (types.either types.str (resource "sns-topic"));
      apply = map (x: if builtins.isString x then x else "res-" + x._name);
      default = [];
      description = ''
        The actions to execute when this alarm transitions to the OK state from
        any other state.
      '';
    };

    insufficientDataActions = mkOption {
      type = types.listOf (types.either types.str (resource "sns-topic"));
      apply = map (x: if builtins.isString x then x else "res-" + x._name);
      default = [];
      description = ''
        The actions to execute when this alarm transitions to the INSUFFICIENT_DATA
        state from any other state.
      '';
    };

    treatMissingData = mkOption {
      type = types.enum [ "breaching" "notBreaching" "ignore" "missing" ];
      default = "missing";
      description = ''
        How this alarm is to handle missing data points.
      '';
    };

    datapointsToAlarm = mkOption {
      type = types.int;
      description = ''
        The number of datapoints that must be breaching to trigger the alarm.
      '';
    };

  };

  config = {
    _type = "cloudwatch-metric-alarm";
  };
}
