import nose
import sys
import os

if __name__ == "__main__":
    config = nose.config.Config(plugins=nose.plugins.manager.DefaultPluginManager())
    config.configure(argv=[sys.argv[0], "-e", "^coverage-tests\.py$"] + sys.argv[1:])
    count = (
        nose.loader.defaultTestLoader(config=config)
        .loadTestsFromNames(["."])
        .countTestCases()
    )
    nose.main(
        argv=[
            sys.argv[0],
            "--process-timeout=inf",
            "--processes=%d".format(count),
            "-e",
            "^coverage-tests\.py$",
        ]
        + sys.argv[1:]
    )
