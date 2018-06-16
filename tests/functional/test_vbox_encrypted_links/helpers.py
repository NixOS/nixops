def ping(deployment, machine1, machine2):
    deployment.machines[machine1].run_command("ping -c1 {0}-encrypted".format(machine2))
