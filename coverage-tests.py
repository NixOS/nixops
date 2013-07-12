import sys
from node import main
from tests import check_for_ec2_envs


if __name__ == "__main__":
    check_for_ec2_envs()
    main(argv=[
        sys.argv[0],
        "--with-xunit",
        "--with-coverage",
        "--cover-inclusive",
        "--cover-xml",
        "--cover-xml-file=coverage.xml",
        "--cover-html",
        "--cover-html-dir=./html",
        "--cover-package=nixops",
        "-e", "^tests\.py$"
    ])
