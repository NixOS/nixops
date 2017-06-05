# -*- coding: utf-8 -*-

# automatic provisioning of aws vpc network ACLs.

import boto3
import botocore
import nixops.util
import nixops.resources
import nixops.resources.ec2_common
import nixops.ec2_utils
from nixops.diff import diff, handler
from nixops.state import statedict

class vpcNetworkAcldefinition(nixops.resources.resourcedefinition):
    """definition of a vpc network ACL."""

    @classmethod
    def get_type(cls):
        return "vpc-network-acl"

    @classmethod
    def get_resource_type(cls):
        return "vpcNetworkAcls"

    def show_type(self):
        return "{0}".format(self.get_type())


class vpcNetworkAclstate(nixops.resources.resourcestate, nixops.resources.ec2_common.ec2commonstate):
    """state of a vpc Network ACL."""


