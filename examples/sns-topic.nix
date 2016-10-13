{ account
, region ? "us-east-1"
, description ? "SNS topic example"
, ...
}:
{
  network.description = description;

  resources.snsTopics.example-topic = {
    name = "sns-topic";
    displayName = "Nixops SNS topic";
    accessKeyId = account;
    subscriptions = [
    {
      protocol = "email";
      endpoint = "amine@chikhaoui.tn";
    }
    ];
    inherit region;
  };
}