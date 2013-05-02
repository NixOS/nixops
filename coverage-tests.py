import nose
import sys
import os

if __name__ == "__main__":
    assert os.getenv("EC2_SECURITY_GROUP") is not None, "The EC2_SECURITY_GROUP env var must be set to the name of an ec2 security group with inbound ssh access"
    assert os.getenv("EC2_KEY_PAIR") is not None, "The EC2_KEY_PAIR env var must be set to the name of an ec2 keypair"
    assert os.getenv("EC2_PRIVATE_KEY_FILE") is not None, "The EC2_PRIVATE_KEY_FILE env var must be set to the private key of an ec2 keypair"
    nose.main(argv=[ sys.argv[0], "--with-xunit", "--with-coverage", "--cover-inclusive", "--cover-xml", "--cover-xml-file=coverage.xml", "--cover-html", "--cover-html-dir=./html", "--cover-package=nixops", "-e", "^tests\.py$" ])
