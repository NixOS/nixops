def deployment_run_command(deployment, command):
    deployment.evaluate()
    machine = deployment.machines.values()[0]
    return machine.run_command(command)
