from os import path
from parameterized import parameterized

from nose import tools
from nose.plugins.attrib import attr
import boto3

from tests.functional.shared.using_unique_state_file import using_unique_state_file
from tests.functional.shared.create_deployment import create_deployment

parent_dir = path.dirname(__file__)

@parameterized([
    'json',
    'nixops'
])
def test_deploy_vpc(state_extension):
    with using_unique_state_file(
            [test_deploy_vpc.__name__],
            state_extension
        ) as state:
        deployment = create_deployment(state, [
            "{}/vpc.nix".format(parent_dir)
        ])

        deployment.deploy()

        vpc_resource = deployment.get_typed_resource("vpc-test", "vpc")
        vpc = vpc_resource.get_client().describe_vpcs(VpcIds=[vpc_resource._state['vpcId']])
        tools.ok_(len(vpc['Vpcs']) > 0, "VPC not found!")
        tools.eq_(vpc['Vpcs'][0]['CidrBlock'], "10.0.0.0/16", "CIDR block mismatch")

@parameterized([
    'json',
    'nixops'
])
def test_deploy_vpc_machine(state_extension):
    with using_unique_state_file(
            [test_deploy_vpc_machine.__name__],
            state_extension
        ) as state:

        nix_expressions = [
            "{}/vpc.nix".format(parent_dir),
            "{}/subnet.nix".format(parent_dir),
            "{}/igw_route.nix".format(parent_dir),
            "{}/network.nix".format(parent_dir),
        ]

        deployment = create_deployment(state, nix_expressions)

        deployment.deploy(plan_only=True)
        deployment.deploy()

@parameterized([
    'json',
    'nixops'
])
def test_enable_dns_support(state_extension):
    with using_unique_state_file(
            [test_enable_dns_support.__name__],
            state_extension
        ) as state:

        nix_expressions = [
            "{}/vpc.nix".format(parent_dir),
            "{}/enable_dns_support.nix".format(parent_dir),
        ]

        deployment = create_deployment(state, nix_expressions)

        deployment.deploy(plan_only=True)
        deployment.deploy()

@parameterized([
    'json',
    'nixops'
])
def test_enable_ipv6(state_extension):
    with using_unique_state_file(
            [test_enable_ipv6.__name__],
            state_extension
        ) as state:
        nix_expressions = [
            "{}/vpc.nix".format(parent_dir),
            "{}/ipv6.nix".format(parent_dir),
        ]

        deployment = create_deployment(state, nix_expressions)

        deployment.deploy(plan_only=True)
        deployment.deploy()

        vpc_resource = deployment.get_typed_resource("vpc-test", "vpc")
        vpc = vpc_resource.get_client().describe_vpcs(VpcIds=[vpc_resource._state['vpcId']])
        ipv6_block = vpc['Vpcs'][0]['Ipv6CidrBlockAssociationSet']
        tools.ok_(len(ipv6_block) > 0, "There is no Ipv6 block")
        tools.ok_(ipv6_block[0].get('Ipv6CidrBlock', None) != None, "No Ipv6 cidr block in the response")

@parameterized([
    'json',
    'nixops'
])
def test_deploy_subnets(state_extension):
    with using_unique_state_file(
            [test_deploy_subnets.__name__],
            state_extension
        ) as state:
        # FIXME might need to factor out resources into separate test
        # classes depending on the number of tests needed.

        nix_expressions = [
            "{}/vpc.nix".format(parent_dir),
            "{}/subnet.nix".format(parent_dir),
        ]

        deployment = create_deployment(state, nix_expressions)

        deployment.deploy(plan_only=True)
        deployment.deploy()
        subnet_resource = deployment.get_typed_resource("subnet-test", "vpc-subnet")
        subnet = subnet_resource.get_client().describe_subnets(SubnetIds=[subnet_resource._state['subnetId']])
        tools.ok_(len(subnet['Subnets']) > 0, "VPC subnet not found!")

@parameterized([
    'json',
    'nixops'
])
def test_deploy_nat_gtw(state_extension):
    with using_unique_state_file(
            [test_deploy_nat_gtw.__name__],
            state_extension
        ) as state:
        nix_expressions = [
            "{}/vpc.nix".format(parent_dir),
            "{}/subnet.nix".format(parent_dir),
            "{}/nat_gtw.nix".format(parent_dir),
        ]

        deployment = create_deployment(state, nix_expressions)

        deployment.deploy(plan_only=True)
        deployment.deploy()
