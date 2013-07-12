import os
import sys
from nose import main
from nose.config import Config
from nose.plugins.manager import DefaultPluginManager
from nose.loader import defaultTestLoader

ERROR1 = "The EC2_SECURITY_GROUP env var must be set to the name of an ec2 "\
         "security group with inbound ssh access"
ERROR2 = "The EC2_KEY_PAIR env var must be set to the name of an ec2 keypair"
ERROR3 = "The EC2_PRIVATE_KEY_FILE env var must be set to the private key of "\
         "an ec2 keypair"


def check_for_ec2_envs():
    assert os.getenv("EC2_SECURITY_GROUP") is not None, ERROR1
    assert os.getenv("EC2_KEY_PAIR") is not None, ERROR2
    assert os.getenv("EC2_PRIVATE_KEY_FILE") is not None, ERROR3


if __name__ == "__main__":
    check_for_ec2_envs()
    config = Config(plugins=DefaultPluginManager())
    config.configure(argv=[sys.argv[0], "-e", "^coverage-tests\.py$"])
    count = defaultTestLoader(config=config)\
        .loadTestsFromNames(['.'])\
        .countTestCases()
    main(argv=[
        sys.argv[0],
        "--process-timeout=inf",
        "--processes=%d" % (count),
        "-e",  "^coverage-tests\.py$"
    ])
