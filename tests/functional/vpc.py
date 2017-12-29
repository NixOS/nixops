from os import path
import tempfile

from nose import tools
from nose.plugins.attrib import attr
import boto3

from nixops.nix_expr import RawValue, Function, Call, py2nix
import nixops.util
from tests.functional import generic_deployment_test

parent_dir = path.dirname(__file__)

base_spec = "{}/vpc.nix".format(parent_dir)

class TestVPC(generic_deployment_test.GenericDeploymentTest):

    def setup(self):
        super(TestVPC,self).setup()
        self.depl.nix_exprs = [ base_spec ]
        self.exprs_dir = nixops.util.SelfDeletingDir(tempfile.mkdtemp("nixos-tests"))

    def test_deploy(self):
        self.depl.deploy()
        vpc_resource = self.depl.get_typed_resource("vpc-nixops", "vpc")
        vpc = vpc_resource.get_client().describe_vpcs(VpcIds=[vpc_resource._state['vpcId']])
        tools.ok_(len(vpc['Vpcs']) > 0, "VPC not found!")
        tools.eq_(vpc['Vpcs'][0]['CidrBlock'], "10.0.0.0/16", "CIDR block mismatch")

    def test_enable_dns_support(self):
        self.depl.nix_exprs = [base_spec ] + [ self.config_enable_dns_support() ]
        self.depl.deploy(plan_only=True)
        self.depl.deploy()

    def test_deploy_subnets(self):
        self.depl.nix_exprs = [ base_spec ] + [ self.config_subnets() ]
        self.depl.deploy(plan_only=True)
        self.depl.deploy()

    def config_subnets(self):
        resources = """
        {
          resources.vpcSubnets =
            let
              region = "us-east-1";
              subnet = {cidr, zone}:
                { resources, ... }:
                {
                  inherit region zone;
                  vpcId = resources.vpc.vpc-nixops;
                  cidrBlock = cidr;
                  mapPublicIpOnLaunch = true;
                  tags = {
                    Source = "NixOps Tests";
                  };
                };
            in
            {
              subnet-a = subnet { cidr = "10.0.0.0/19"; zone = "us-east-1a"; };
              subnet-b = subnet { cidr = "10.0.32.0/19"; zone = "us-east-1b"; };
            };
        }
        """
        path = "{}/vpc_subnets.nix".format(self.exprs_dir)
        with open(path, "w") as cfg:
            cfg.write(resources)
        return path

    def config_enable_dns_support(self):
        enable_dns_support = py2nix({
              ( 'resources', 'vpc', 'vpc-nixops', 'enableDnsSupport'): True
            })
        path = "{}/dns_support.nix".format(self.exprs_dir)
        with open(path, "w") as cfg:
            cfg.write(enable_dns_support)
        return path
