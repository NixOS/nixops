#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os


def setup_debugger() -> None:
    """
    """
    import traceback
    import pdb
    from types import TracebackType
    from typing import Type

    def hook(
        _type: Type[BaseException], value: BaseException, tb: TracebackType
    ) -> None:
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


from nixops.parallel import MultipleExceptions
from nixops.script_defs import setup_logging
from nixops.evaluation import NixEvalError
from nixops.script_defs import error
from nixops.args import parser
import nixops


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
    except NixEvalError:
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
