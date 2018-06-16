def create_deployment(state, nix_expressions=[]):
    deployment = state.create_deployment()
    deployment.logger.set_autoresponse("y")
    deployment.nix_exprs = nix_expressions
    return deployment
