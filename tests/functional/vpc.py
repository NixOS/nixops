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

    def test_deploy_vpc(self):
        self.depl.deploy()
        vpc_resource = self.depl.get_typed_resource("vpc-test", "vpc")
        vpc = vpc_resource.get_client().describe_vpcs(VpcIds=[vpc_resource._state['vpcId']])
        tools.ok_(len(vpc['Vpcs']) > 0, "VPC not found!")
        tools.eq_(vpc['Vpcs'][0]['CidrBlock'], "10.0.0.0/16", "CIDR block mismatch")

    def test_enable_dns_support(self):
        self.depl.nix_exprs = [base_spec ] + [ self.config_enable_dns_support() ]
        self.depl.deploy(plan_only=True)
        self.depl.deploy()

    def test_enable_ipv6(self):
        self.depl.nix_exprs = [base_spec ] + [ self.config_enable_ipv6() ]
        self.depl.deploy(plan_only=True)
        self.depl.deploy()
        vpc_resource = self.depl.get_typed_resource("vpc-test", "vpc")
        vpc = vpc_resource.get_client().describe_vpcs(VpcIds=[vpc_resource._state['vpcId']])
        ipv6_block = vpc['Vpcs'][0]['Ipv6CidrBlockAssociationSet']
        tools.ok_(len(ipv6_block) > 0, "There is no Ipv6 block")
        tools.ok_(ipv6_block[0].get('Ipv6CidrBlock', None) != None, "No Ipv6 cidr block in the response")

    def test_deploy_subnets(self):
        # FIXME might need to factor out resources into separate test
        # classes depending on the number of tests needed.
        self.depl.nix_exprs = [ base_spec ] + [ self.config_subnets() ]
        self.depl.deploy(plan_only=True)
        self.depl.deploy()
        subnet_resource = self.depl.get_typed_resource("subnet-test", "vpc-subnet")
        subnet = subnet_resource.get_client().describe_subnets(SubnetIds=[subnet_resource._state['subnetId']])
        tools.ok_(len(subnet['Subnets']) > 0, "VPC subnet not found!")

    def config_subnets(self):
        resources = """
        {
          resources.vpcSubnets.subnet-test =
            { resources, ... }:
            {
              region = "us-east-1";
              zone = "us-east-1a";
              vpcId = resources.vpc.vpc-test;
              cidrBlock = "10.0.0.0/19";
              mapPublicIpOnLaunch = true;
              tags = {
                Source = "NixOps Tests";
              };
            };
        }
        """
        path = "{}/vpc_subnets.nix".format(self.exprs_dir)
        with open(path, "w") as cfg:
            cfg.write(resources)
        return path

    def config_enable_dns_support(self):
        enable_dns_support = py2nix({
              ( 'resources', 'vpc', 'vpc-test', 'enableDnsSupport'): True
            })
        path = "{}/dns_support.nix".format(self.exprs_dir)
        with open(path, "w") as cfg:
            cfg.write(enable_dns_support)
        return path

    def config_enable_ipv6(self):
        enable_ipv6 = py2nix({
            ( 'resources', 'vpc', 'vpc-test','amazonProvidedIpv6CidrBlock'): True
            })
        path = "{}/vpc_ipv6.nix".format(self.exprs_dir)
        with open(path, "w") as cfg:
            cfg.write(enable_ipv6)
        return path
