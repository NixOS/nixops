#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import sys


def setup_debugger() -> None:
    """
    """
    import traceback
    import pdb
    from types import TracebackType
    from typing import Type

    def hook(_type: Type[BaseException], value: BaseException, tb: TracebackType):
        if hasattr(sys, "ps1") or not sys.stderr.isatty():
            sys.__excepthook__(_type, value, tb)
        else:
            traceback.print_exception(_type, value, tb)
            pdb.post_mortem(tb)

    sys.excepthook = hook


# Run check for --pdb as early as possible so it kicks in _before_ plugin loading
# and other dynamic startup happens
if __name__.split(".")[-1] == "__main__":
    if "--pdb" in sys.argv:
        setup_debugger()


from argparse import ArgumentParser, _SubParsersAction, SUPPRESS, REMAINDER
import os
from nixops.parallel import MultipleExceptions
from nixops.script_defs import (
    add_subparser,
    op_list_deployments,
    op_create,
    add_common_modify_options,
    op_modify,
    op_clone,
    op_delete,
    op_info,
    op_check,
    op_set_args,
    op_deploy,
    add_common_deployment_options,
    op_send_keys,
    op_destroy,
    op_delete_resources,
    op_stop,
    op_start,
    op_reboot,
    op_show_arguments,
    op_show_physical,
    op_ssh,
    op_ssh_for_each,
    op_scp,
    op_mount,
    op_rename,
    op_backup,
    op_backup_status,
    op_remove_backup,
    op_clean_backups,
    op_restore,
    op_show_option,
    op_list_generations,
    op_rollback,
    op_delete_generation,
    op_show_console_output,
    op_dump_nix_paths,
    op_export,
    op_import,
    op_edit,
    op_copy_closure,
    op_list_plugins,
    parser_plugin_hooks,
    setup_logging,
    error,
)
import sys
import nixops
import nixops.ansi

# Set up the parser.
parser = ArgumentParser(description="NixOS cloud deployment tool", prog="nixops")
parser.add_argument("--version", action="version", version="NixOps @version@")
parser.add_argument(
    "--pdb", action="store_true", help="Invoke pdb on unhandled exception"
)

subparsers: _SubParsersAction = parser.add_subparsers(
    help="sub-command help", metavar="operation", required=True
)

subparser = add_subparser(subparsers, "list", help="list all known deployments")
subparser.set_defaults(op=op_list_deployments)

subparser = add_subparser(subparsers, "create", help="create a new deployment")
subparser.set_defaults(op=op_create)
subparser.add_argument(
    "--name", "-n", dest="name", metavar="NAME", help=SUPPRESS
)  # obsolete, use -d instead
add_common_modify_options(subparser)

subparser = add_subparser(subparsers, "modify", help="modify an existing deployment")
subparser.set_defaults(op=op_modify)
subparser.add_argument(
    "--name", "-n", dest="name", metavar="NAME", help="new symbolic name of deployment"
)
add_common_modify_options(subparser)

subparser = add_subparser(subparsers, "clone", help="clone an existing deployment")
subparser.set_defaults(op=op_clone)
subparser.add_argument(
    "--name",
    "-n",
    dest="name",
    metavar="NAME",
    help="symbolic name of the cloned deployment",
)

subparser = add_subparser(subparsers, "delete", help="delete a deployment")
subparser.add_argument(
    "--force", action="store_true", help="force deletion even if resources still exist"
)
subparser.add_argument("--all", action="store_true", help="delete all deployments")
subparser.set_defaults(op=op_delete)

subparser = add_subparser(subparsers, "info", help="show the state of the deployment")
subparser.set_defaults(op=op_info)
subparser.add_argument("--all", action="store_true", help="show all deployments")
subparser.add_argument(
    "--plain", action="store_true", help="do not pretty-print the output"
)
subparser.add_argument(
    "--no-eval",
    action="store_true",
    help="do not evaluate the deployment specification",
)

subparser = add_subparser(
    subparsers,
    "check",
    help="check the state of the machines in the network"
    " (note that this might alter the internal nixops state to consolidate with the real state of the resource)",
)
subparser.set_defaults(op=op_check)
subparser.add_argument("--all", action="store_true", help="check all deployments")
subparser.add_argument(
    "--include",
    nargs="+",
    metavar="MACHINE-NAME",
    help="check only the specified machines",
)
subparser.add_argument(
    "--exclude",
    nargs="+",
    metavar="MACHINE-NAME",
    help="check all except the specified machines",
)

subparser = add_subparser(
    subparsers,
    "set-args",
    help="persistently set arguments to the deployment specification",
)
subparser.set_defaults(op=op_set_args)
subparser.add_argument(
    "--arg",
    nargs=2,
    action="append",
    dest="args",
    metavar=("NAME", "VALUE"),
    help="pass a Nix expression value",
)
subparser.add_argument(
    "--argstr",
    nargs=2,
    action="append",
    dest="argstrs",
    metavar=("NAME", "VALUE"),
    help="pass a string value",
)
subparser.add_argument(
    "--unset",
    nargs=1,
    action="append",
    dest="unset",
    metavar="NAME",
    help="unset previously set argument",
)


subparser = add_subparser(subparsers, "deploy", help="deploy the network configuration")
subparser.set_defaults(op=op_deploy)
subparser.add_argument(
    "--kill-obsolete", "-k", action="store_true", help="kill obsolete virtual machines"
)
subparser.add_argument(
    "--dry-run", action="store_true", help="evaluate and print what would be built"
)
subparser.add_argument(
    "--dry-activate",
    action="store_true",
    help="show what will be activated on the machines in the network",
)
subparser.add_argument(
    "--test",
    action="store_true",
    help="build and activate the new configuration; do not enable it in the bootloader. Rebooting the system will roll back automatically.",
)
subparser.add_argument(
    "--boot",
    action="store_true",
    help="build the new configuration and enable it in the bootloader; do not activate it. Upon reboot, the system will use the new configuration.",
)
subparser.add_argument(
    "--repair", action="store_true", help="use --repair when calling nix-build (slow)"
)
subparser.add_argument(
    "--evaluate-only", action="store_true", help="only call nix-instantiate and exit"
)
subparser.add_argument(
    "--plan-only",
    action="store_true",
    help="show the diff between the configuration and the state and exit",
)
subparser.add_argument(
    "--build-only",
    action="store_true",
    help="build only; do not perform deployment actions",
)
subparser.add_argument(
    "--create-only", action="store_true", help="exit after creating missing machines"
)
subparser.add_argument(
    "--copy-only", action="store_true", help="exit after copying closures"
)
subparser.add_argument(
    "--allow-recreate",
    action="store_true",
    help="recreate resources machines that have disappeared",
)
subparser.add_argument(
    "--always-activate",
    action="store_true",
    help="activate unchanged configurations as well",
)
add_common_deployment_options(subparser)

subparser = add_subparser(subparsers, "send-keys", help="send encryption keys")
subparser.set_defaults(op=op_send_keys)
subparser.add_argument(
    "--include",
    nargs="+",
    metavar="MACHINE-NAME",
    help="send keys to only the specified machines",
)
subparser.add_argument(
    "--exclude",
    nargs="+",
    metavar="MACHINE-NAME",
    help="send keys to all except the specified machines",
)

subparser = add_subparser(
    subparsers, "destroy", help="destroy all resources in the specified deployment"
)
subparser.set_defaults(op=op_destroy)
subparser.add_argument(
    "--include",
    nargs="+",
    metavar="MACHINE-NAME",
    help="destroy only the specified machines",
)
subparser.add_argument(
    "--exclude",
    nargs="+",
    metavar="MACHINE-NAME",
    help="destroy all except the specified machines",
)
subparser.add_argument(
    "--wipe", action="store_true", help="securely wipe data on the machines"
)
subparser.add_argument("--all", action="store_true", help="destroy all deployments")

subparser = add_subparser(
    subparsers,
    "delete-resources",
    help="deletes the resource from the local NixOps state file.",
)
subparser.set_defaults(op=op_delete_resources)
subparser.add_argument(
    "--include",
    nargs="+",
    metavar="RESOURCE-NAME",
    help="delete only the specified resources",
)
subparser.add_argument(
    "--exclude",
    nargs="+",
    metavar="RESOURCE-NAME",
    help="delete all resources except the specified resources",
)

subparser = add_subparser(
    subparsers, "stop", help="stop all virtual machines in the network"
)
subparser.set_defaults(op=op_stop)
subparser.add_argument(
    "--include",
    nargs="+",
    metavar="MACHINE-NAME",
    help="stop only the specified machines",
)
subparser.add_argument(
    "--exclude",
    nargs="+",
    metavar="MACHINE-NAME",
    help="stop all except the specified machines",
)

subparser = add_subparser(
    subparsers, "start", help="start all virtual machines in the network"
)
subparser.set_defaults(op=op_start)
subparser.add_argument(
    "--include",
    nargs="+",
    metavar="MACHINE-NAME",
    help="start only the specified machines",
)
subparser.add_argument(
    "--exclude",
    nargs="+",
    metavar="MACHINE-NAME",
    help="start all except the specified machines",
)

subparser = add_subparser(
    subparsers, "reboot", help="reboot all virtual machines in the network"
)
subparser.set_defaults(op=op_reboot)
subparser.add_argument(
    "--include",
    nargs="+",
    metavar="MACHINE-NAME",
    help="reboot only the specified machines",
)
subparser.add_argument(
    "--exclude",
    nargs="+",
    metavar="MACHINE-NAME",
    help="reboot all except the specified machines",
)
subparser.add_argument(
    "--no-wait", action="store_true", help="do not wait until the machines are up again"
)
subparser.add_argument(
    "--rescue",
    action="store_true",
    help="reboot machines into the rescue system" " (if available)",
)
subparser.add_argument(
    "--hard",
    action="store_true",
    help="send a hard reset (power switch) to the machines" " (if available)",
)

subparser = add_subparser(
    subparsers, "show-arguments", help="print the arguments to the network expressions"
)
subparser.set_defaults(op=op_show_arguments)

subparser = add_subparser(
    subparsers, "show-physical", help="print the physical network expression"
)
subparser.add_argument(
    "--backup",
    dest="backupid",
    default=None,
    help="print physical network expression for given backup id",
)
subparser.set_defaults(op=op_show_physical)

subparser = add_subparser(
    subparsers, "ssh", help="login on the specified machine via SSH"
)
subparser.set_defaults(op=op_ssh)
subparser.add_argument("machine", metavar="MACHINE", help="identifier of the machine")
subparser.add_argument(
    "args", metavar="SSH_ARGS", nargs=REMAINDER, help="SSH flags and/or command",
)

subparser = add_subparser(
    subparsers, "ssh-for-each", help="execute a command on each machine via SSH"
)
subparser.set_defaults(op=op_ssh_for_each)
subparser.add_argument(
    "args", metavar="ARG", nargs="*", help="additional arguments to SSH"
)
subparser.add_argument("--parallel", "-p", action="store_true", help="run in parallel")
subparser.add_argument(
    "--include",
    nargs="+",
    metavar="MACHINE-NAME",
    help="run command only on the specified machines",
)
subparser.add_argument(
    "--exclude",
    nargs="+",
    metavar="MACHINE-NAME",
    help="run command on all except the specified machines",
)
subparser.add_argument(
    "--all", action="store_true", help="run ssh-for-each for all deployments"
)

subparser = add_subparser(
    subparsers, "scp", help="copy files to or from the specified machine via scp"
)
subparser.set_defaults(op=op_scp)
subparser.add_argument(
    "--from",
    dest="scp_from",
    action="store_true",
    help="copy a file from specified machine",
)
subparser.add_argument(
    "--to", dest="scp_to", action="store_true", help="copy a file to specified machine"
)
subparser.add_argument("machine", metavar="MACHINE", help="identifier of the machine")
subparser.add_argument("source", metavar="SOURCE", help="source file location")
subparser.add_argument("destination", metavar="DEST", help="destination file location")

subparser = add_subparser(
    subparsers,
    "mount",
    help="mount a directory from the specified machine into the local filesystem",
)
subparser.set_defaults(op=op_mount)
subparser.add_argument(
    "machine",
    metavar="MACHINE[:PATH]",
    help="identifier of the machine, optionally followed by a path",
)
subparser.add_argument("destination", metavar="PATH", help="local path")
subparser.add_argument(
    "--sshfs-option",
    "-o",
    action="append",
    metavar="OPTIONS",
    help="mount options passed to sshfs",
)

subparser = add_subparser(subparsers, "rename", help="rename machine in network")
subparser.set_defaults(op=op_rename)
subparser.add_argument(
    "current_name", metavar="FROM", help="current identifier of the machine"
)
subparser.add_argument("new_name", metavar="TO", help="new identifier of the machine")

subparser = add_subparser(
    subparsers,
    "backup",
    help="make snapshots of persistent disks in network (currently EC2-only)",
)
subparser.set_defaults(op=op_backup)
subparser.add_argument(
    "--include",
    nargs="+",
    metavar="MACHINE-NAME",
    help="perform backup actions on the specified machines only",
)
subparser.add_argument(
    "--exclude",
    nargs="+",
    metavar="MACHINE-NAME",
    help="do not perform backup actions on the specified machines",
)
subparser.add_argument(
    "--freeze",
    dest="freeze_fs",
    action="store_true",
    default=False,
    help="freeze filesystems for non-root filesystems that support this (e.g. xfs)",
)
subparser.add_argument(
    "--force",
    dest="force",
    action="store_true",
    default=False,
    help="start new backup even if previous is still running",
)
subparser.add_argument(
    "--devices",
    nargs="+",
    metavar="DEVICE-NAME",
    help="only backup the specified devices",
)

subparser = add_subparser(subparsers, "backup-status", help="get status of backups")
subparser.set_defaults(op=op_backup_status)
subparser.add_argument(
    "backupid", default=None, nargs="?", help="use specified backup in stead of latest"
)
subparser.add_argument(
    "--include",
    nargs="+",
    metavar="MACHINE-NAME",
    help="perform backup actions on the specified machines only",
)
subparser.add_argument(
    "--exclude",
    nargs="+",
    metavar="MACHINE-NAME",
    help="do not perform backup actions on the specified machines",
)
subparser.add_argument(
    "--wait",
    dest="wait",
    action="store_true",
    default=False,
    help="wait until backup is finished",
)
subparser.add_argument(
    "--latest",
    dest="latest",
    action="store_true",
    default=False,
    help="show status of latest backup only",
)

subparser = add_subparser(subparsers, "remove-backup", help="remove a given backup")
subparser.set_defaults(op=op_remove_backup)
subparser.add_argument("backupid", metavar="BACKUP-ID", help="backup ID to remove")
subparser.add_argument(
    "--keep-physical",
    dest="keep_physical",
    default=False,
    action="store_true",
    help="do not remove the physical backups, only remove backups from nixops state",
)

subparser = add_subparser(subparsers, "clean-backups", help="remove old backups")
subparser.set_defaults(op=op_clean_backups)
subparser.add_argument(
    "--keep", dest="keep", type=int, help="number of backups to keep around"
)
subparser.add_argument(
    "--keep-days",
    metavar="N",
    dest="keep_days",
    type=int,
    help="keep backups newer than N days",
)
subparser.add_argument(
    "--keep-physical",
    dest="keep_physical",
    default=False,
    action="store_true",
    help="do not remove the physical backups, only remove backups from nixops state",
)

subparser = add_subparser(
    subparsers,
    "restore",
    help="restore machines based on snapshots of persistent disks in network (currently EC2-only)",
)
subparser.set_defaults(op=op_restore)
subparser.add_argument(
    "--backup-id", default=None, help="use specified backup in stead of latest"
)
subparser.add_argument(
    "--include",
    nargs="+",
    metavar="MACHINE-NAME",
    help="perform backup actions on the specified machines only",
)
subparser.add_argument(
    "--exclude",
    nargs="+",
    metavar="MACHINE-NAME",
    help="do not perform backup actions on the specified machines",
)
subparser.add_argument(
    "--devices",
    nargs="+",
    metavar="DEVICE-NAME",
    help="only restore the specified devices",
)

subparser = add_subparser(
    subparsers, "show-option", help="print the value of a configuration option"
)
subparser.set_defaults(op=op_show_option)
subparser.add_argument("machine", metavar="MACHINE", help="identifier of the machine")
subparser.add_argument("option", metavar="OPTION", help="option name")
subparser.add_argument(
    "--xml", action="store_true", help="print the option value in XML format"
)
subparser.add_argument(
    "--json", action="store_true", help="print the option value in JSON format"
)
subparser.add_argument(
    "--include-physical",
    action="store_true",
    help="include the physical specification in the evaluation",
)

subparser = add_subparser(
    subparsers,
    "list-generations",
    help="list previous configurations to which you can roll back",
)
subparser.set_defaults(op=op_list_generations)

subparser = add_subparser(
    subparsers, "rollback", help="roll back to a previous configuration"
)
subparser.set_defaults(op=op_rollback)
subparser.add_argument(
    "generation",
    type=int,
    metavar="GENERATION",
    help="number of the desired configuration (see ‘nixops list-generations’)",
)
add_common_deployment_options(subparser)

subparser = add_subparser(
    subparsers, "delete-generation", help="remove a previous configuration"
)
subparser.set_defaults(op=op_delete_generation)
subparser.add_argument(
    "generation",
    type=int,
    metavar="GENERATION",
    help="number of the desired configuration (see ‘nixops list-generations’)",
)
add_common_deployment_options(subparser)

subparser = add_subparser(
    subparsers,
    "show-console-output",
    help="print the machine's console output on stdout",
)
subparser.set_defaults(op=op_show_console_output)
subparser.add_argument("machine", metavar="MACHINE", help="identifier of the machine")
add_common_deployment_options(subparser)

subparser = add_subparser(
    subparsers, "dump-nix-paths", help="dump Nix paths referenced in deployments"
)
subparser.add_argument(
    "--all", action="store_true", help="dump Nix paths for all deployments"
)
subparser.set_defaults(op=op_dump_nix_paths)
add_common_deployment_options(subparser)

subparser = add_subparser(subparsers, "export", help="export the state of a deployment")
subparser.add_argument("--all", action="store_true", help="export all deployments")
subparser.set_defaults(op=op_export)

subparser = add_subparser(
    subparsers, "import", help="import deployments into the state file"
)
subparser.add_argument(
    "--include-keys",
    action="store_true",
    help="import public SSH hosts keys to .ssh/known_hosts",
)
subparser.set_defaults(op=op_import)

subparser = add_subparser(
    subparsers, "edit", help="open the deployment specification in $EDITOR"
)
subparser.set_defaults(op=op_edit)

subparser = add_subparser(
    subparsers, "copy-closure", help="copy closure to a target machine"
)
subparser.add_argument("machine", help="identifier of the machine")
subparser.add_argument("storepath", help="store path of the closure to be copied")
subparser.set_defaults(op=op_copy_closure)

subparser = subparsers.add_parser(
    "list-plugins", help="list the available nixops plugins"
)
subparser.set_defaults(op=op_list_plugins)
subparser.add_argument(
    "--verbose", "-v", action="store_true", help="Provide extra plugin information"
)
subparser.add_argument("--debug", action="store_true", help="enable debug output")

parser_plugin_hooks(parser, subparsers)


def main() -> None:

    if os.path.basename(sys.argv[0]) == "charon":
        sys.stderr.write(
            nixops.ansi.ansi_warn("warning: ‘charon’ is now called ‘nixops’") + "\n"
        )

    args = parser.parse_args()
    setup_logging(args)

    from nixops.exceptions import NixError

    try:
        nixops.deployment.DEBUG = args.debug
        args.op(args)
    except nixops.deployment.NixEvalError:
        error("evaluation of the deployment specification failed")
        sys.exit(1)
    except KeyboardInterrupt:
        error("interrupted")
        sys.exit(1)
    except MultipleExceptions as e:
        error(str(e))
        if args.debug or args.show_trace or str(e) == "":
            e.print_all_backtraces()
        sys.exit(1)
    except NixError as e:
        sys.stderr.write(str(e))
        sys.stderr.flush()
        sys.exit(1)


if __name__ == "__main__":
    main()
