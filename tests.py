import nose
import sys
import os

if __name__ == "__main__":
    assert os.getenv("EC2_SECURITY_GROUP") is not None, "The EC2_SECURITY_GROUP env var must be set to the name of an ec2 security group with inbound ssh access"
    assert os.getenv("EC2_KEY_PAIR") is not None, "The EC2_KEY_PAIR env var must be set to the name of an ec2 keypair"
    assert os.getenv("EC2_PRIVATE_KEY_FILE") is not None, "The EC2_PRIVATE_KEY_FILE env var must be set to the private key of an ec2 keypair"
    config = nose.config.Config(plugins=nose.plugins.manager.DefaultPluginManager())
    config.configure(argv=[sys.argv[0], "-e", "^coverage-tests\.py$"])
    count = nose.loader.defaultTestLoader(config=config).loadTestsFromNames(['.']).countTestCases()
    nose.main(argv=[sys.argv[0], "--process-timeout=inf", "--processes=%d" % (count), "-e", "^coverage-tests\.py$"])
