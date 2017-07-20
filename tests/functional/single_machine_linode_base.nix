{
  machine =
    { resources, ... }:
    {
      deployment.targetEnv = "linode";
      deployment.linode = {
        personalAPIKey = "";
      };
    };
}
