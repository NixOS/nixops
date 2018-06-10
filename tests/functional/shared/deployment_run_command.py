from nixops.util import ansi_highlight

def deployment_run_command(deployment, command, michine_index=0):
    deployment.evaluate()
    machine = deployment.machines.values()[michine_index]

    debug_message = ansi_highlight('tests> ') + command
    import sys; print >> sys.__stdout__, debug_message

    return machine.run_command(command)
