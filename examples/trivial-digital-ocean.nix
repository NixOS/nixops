{
  machine =
    { deployment.targetEnv = "digital-ocean";
      deployment.digital-ocean.region = "nyc3";
      deployment.digital-ocean.size = "512mb";
      deployment.digital-ocean.keyName = "teh";
      deployment.digital-ocean.authToken = "TODO-fill-me-in";
    };
}
