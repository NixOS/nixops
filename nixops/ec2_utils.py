# -*- coding: utf-8 -*-

from __future__ import absolute_import

import os
import time
import random

from botocore import credentials
from typing import Optional, Callable, List, TypeVar, Dict, Mapping, TYPE_CHECKING, Container

import nixops.util

import boto3
import boto.ec2
import boto.vpc
import logging
from boto.exception import EC2ResponseError
from boto.exception import SQSError
from boto.exception import BotoServerError
from botocore.exceptions import ClientError
from boto.pyami.config import Config

import botocore.session
import botocore.exceptions

from nixops.resources import ResourceState

if TYPE_CHECKING:
    from nixops.resources.ec2_common import EC2CommonState
    T = TypeVar('T')


def fetch_aws_secret_key(access_key_id):
    """
        Fetch the secret access key corresponding to the given access key ID from ~/.ec2-keys,
        or from ~/.aws/credentials, or from the environment (in that priority).
    """

    def parse_ec2_keys():
        path = os.path.expanduser("~/.ec2-keys")
        if os.path.isfile(path):
            with open(path, 'r') as f:
                contents = f.read()
                for l in contents.splitlines():
                    l = l.split("#")[0] # drop comments
                    w = l.split()
                    if len(w) < 2 or len(w) > 3: continue
                    if len(w) == 3 and w[2] == access_key_id: return (w[0], w[1])
                    if w[0] == access_key_id: return (access_key_id, w[1])
        return None

    def parse_aws_credentials():
        path = os.getenv('AWS_SHARED_CREDENTIALS_FILE', "~/.aws/credentials")
        if not os.path.exists(os.path.expanduser(path)):
            return None

        conf = Config(os.path.expanduser(path))

        if access_key_id == conf.get('default', 'aws_access_key_id'):
            return (access_key_id, conf.get('default', 'aws_secret_access_key'))
        return (conf.get(access_key_id, 'aws_access_key_id'),
                conf.get(access_key_id, 'aws_secret_access_key'))

    def ec2_keys_from_env():
        return (access_key_id,
                os.environ.get('EC2_SECRET_KEY') or os.environ.get('AWS_SECRET_ACCESS_KEY'))

    sources = (get_credentials() for get_credentials in
                [parse_ec2_keys, parse_aws_credentials, ec2_keys_from_env])
    # Get the first existing access-secret key pair
    credentials = next( (keys for keys in sources if keys and keys[1]), None)

    return credentials


def session(**kwargs):
    # type: (**str) -> boto3.Session
    # TODO: remove me
    print("session", kwargs)

    kwargs = kwargs.copy()
    profile = kwargs.pop('profile_name', None)

    # cache MFA session between runs so we don't have to enter the code every time
    cli_cache = os.path.join(os.path.expanduser('~'), '.aws/cli/cache')
    session = botocore.session.Session(profile=profile)
    resolver = session.get_component('credential_provider')
    provider = resolver.get_provider('assume-role')
    provider.cache = credentials.JSONFileCache(cli_cache)

    return boto3.session.Session(botocore_session=session, **kwargs)


def connect(region, profile, access_key_id):
    """Connect to the specified EC2 region using the given access key."""
    print("connect", region, profile, access_key_id)
    assert region
    credentials = fetch_aws_secret_key(access_key_id)
    if credentials:
        (access_key_id, secret_access_key) = credentials
        conn = boto.ec2.connect_to_region(
            region_name=region, aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)
    else:
        conn = boto.ec2.connect_to_region(region_name=region, profile_name=profile)

    if not conn:
        raise Exception("invalid EC2 region ‘{0}’".format(region))

    return conn

def connect_ec2_boto3(region, profile, access_key_id):
    print("connect3", region, profile, access_key_id)
    assert region
    credentials = fetch_aws_secret_key(access_key_id)
    if credentials:
        (access_key_id, secret_access_key) = credentials
        client = boto3.session.Session().client('ec2', region_name=region, aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)
    else:
        client = boto3.session.Session(region_name=region, profile_name=profile)
    return client

def connect_vpc(region, access_key_id):
    """Connect to the specified VPC region using the given access key."""
    assert region
    (access_key_id, secret_access_key) = fetch_aws_secret_key(access_key_id)
    conn = boto.vpc.connect_to_region(
        region_name=region, aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)
    if not conn:
        raise Exception("invalid VPC region ‘{0}’".format(region))
    return conn


def get_access_key_id():
    return os.environ.get('EC2_ACCESS_KEY') or os.environ.get('AWS_ACCESS_KEY_ID')


def retry(f, error_codes=None, logger=None):
    # type: (Callable[[], T], Optional[List[str]], Optional[EC2CommonState]) -> T
    """
        Retry function f up to 7 times. If error_codes argument is empty list, retry on all EC2 response errors,
        otherwise, only on the specified error codes.
    """
    if error_codes is None:
        error_codes = []

    def handle_exception(e):
        # type: (botocore.exceptions.ClientError) -> None

        err_code = e.response['Error']['Code']
        err_msg = e.response['Error']['Message']

        if i == num_retries or (error_codes and not err_code in error_codes):
            raise e

        if logger is not None:
            logger.logger.log("got (possibly transient) EC2 error code '%s': %s. retrying..." % (err_code, err_msg))

    i = 0
    num_retries = 7
    while i <= num_retries:
        i += 1
        next_sleep = 5 + random.random() * (2 ** i)

        try:
            return f()
        except ClientError as e:
            if e.response['Error']['Code'] == "RequestLimitExceeded":
                num_retries += 1
                continue
            handle_exception(e)

        time.sleep(next_sleep)


def get_volume_by_id(session, volume_id, allow_missing=False):
    # type: (boto3.Session, str, bool) -> Optional[...]
    """Get volume object by volume id."""
    ec2 = session.resource('ec2')
    volume = ec2.Volume(volume_id)
    try:
        volume.load()
        return volume
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'InvalidVolume.NotFound':
            return None
        raise


def wait_for_volume_available(session, volume_id, logger, states=None):
    # type: (boto3.Session, str, ResourceState, Optional[Container[str]]) -> None
    """Wait for an EBS volume to become available."""

    if states is None:
        states = ['available']

    logger.log_start("waiting for volume ‘{0}’ to become available... ".format(volume_id))

    def check_available():
        # type: () -> bool

        # Allow volume to be missing due to eventual consistency.
        volume = get_volume_by_id(session, volume_id, allow_missing=True)
        logger.log_continue("[{0}] ".format(volume.status))
        return volume.state in states

    nixops.util.check_wait(check_available, max_tries=90)

    logger.log_end('')


def name_to_security_group(session, name, vpc_id):
    # type: (boto3.Session, str, str) -> str
    if not vpc_id or name.startswith('sg-'):
        return name

    ec2 = session.client('ec2')
    for sg in ec2.describe_security_groups(Filters=[{'Name': 'group-name', 'Values': [name]}, {'Name': 'vpc-id', 'Values': [vpc_id]}])['SecurityGroups']:
        if sg['GroupName'] == name:
            return sg['GroupId']
    else:
        raise Exception("could not resolve security group name '{0}' in VPC '{1}'".format(name, vpc_id))


def id_to_security_group_name(conn, sg_id, vpc_id):
    name = None
    for sg in conn.get_all_security_groups(filters={'group-id':sg_id, 'vpc-id': vpc_id}):
        if sg.id == sg_id:
            name = sg.name
            return name
    raise Exception("could not resolve security group id '{0}' in VPC '{1}'".format(sg_id, vpc_id))


def key_value_to_ec2_key_value(kv):
    # type: (Mapping[str, str]) -> List[Dict[str, str]]

    return [{'Key': key, 'Value': value} for key, value in kv.items()]
