# -*- coding: utf-8 -*-

import os
import time
import random

import nixops.util

import boto3
import boto.ec2
import boto.vpc
from boto.exception import EC2ResponseError
from boto.exception import SQSError
from boto.exception import BotoServerError
from botocore.exceptions import ClientError
from boto.pyami.config import Config

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

    if not credentials:
        raise Exception("please set $EC2_SECRET_KEY or $AWS_SECRET_ACCESS_KEY, or add the key for ‘{0}’ to ~/.ec2-keys or ~/.aws/credentials"
                        .format(access_key_id))

    return credentials

def connect(region, access_key_id):
    """Connect to the specified EC2 region using the given access key."""
    assert region
    (access_key_id, secret_access_key) = fetch_aws_secret_key(access_key_id)
    conn = boto.ec2.connect_to_region(
        region_name=region, aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)
    if not conn:
        raise Exception("invalid EC2 region ‘{0}’".format(region))
    return conn

def connect_ec2_boto3(region, access_key_id):
    assert region
    (access_key_id, secret_access_key) = fetch_aws_secret_key(access_key_id)
    client = boto3.session.Session().client('ec2', region_name=region, aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)
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


def retry(f, error_codes=[], logger=None):
    """
        Retry function f up to 7 times. If error_codes argument is empty list, retry on all EC2 response errors,
        otherwise, only on the specified error codes.
    """

    def handle_exception(e):
        if i == num_retries or (error_codes != [] and not e.error_code in error_codes or not 'Error' in e.response.keys() ):
            raise e
        if logger is not None:
            if hasattr(e, 'response'):
                logger.log("got (possibly transient) EC2 error '{}'. retrying...".format(str(e.response['Error'])))
            else:
                logger.log("got (possibly transient) EC2 error code '{0}': {1}. retrying...".format(e.error_code, e.error_message))

    i = 0
    num_retries = 7
    while i <= num_retries:
        i += 1
        next_sleep = 5 + random.random() * (2 ** i)

        try:
            return f()
        except EC2ResponseError as e:
            handle_exception(e)
        except SQSError as e:
            handle_exception(e)
        except ClientError as e:
            handle_exception(e)
        except BotoServerError as e:
            if e.error_code == "RequestLimitExceeded":
                num_retries += 1
            else:
                handle_exception(e)
        except Exception as e:
            raise e

        time.sleep(next_sleep)


def get_volume_by_id(conn, volume_id, allow_missing=False):
    """Get volume object by volume id."""
    try:
        volumes = conn.get_all_volumes([volume_id])
        if len(volumes) != 1:
            raise Exception("unable to find volume ‘{0}’".format(volume_id))
        return volumes[0]
    except boto.exception.EC2ResponseError as e:
        if e.error_code != "InvalidVolume.NotFound": raise
    return None


def wait_for_volume_available(conn, volume_id, logger, states=['available']):
    """Wait for an EBS volume to become available."""

    logger.log_start("waiting for volume ‘{0}’ to become available... ".format(volume_id))

    def check_available():
        # Allow volume to be missing due to eventual consistency.
        volume = get_volume_by_id(conn, volume_id, allow_missing=True)
        logger.log_continue("[{0}] ".format(volume.status))
        return volume.status in states

    nixops.util.check_wait(check_available, max_tries=90)

    logger.log_end('')


def name_to_security_group(conn, name, vpc_id):
    if not vpc_id or name.startswith('sg-'):
        return name

    id = None
    for sg in conn.get_all_security_groups(filters={'group-name':name, 'vpc-id': vpc_id}):
        if sg.name == name:
            id = sg.id
            return id

    raise Exception("could not resolve security group name '{0}' in VPC '{1}'".format(name, vpc_id))

def id_to_security_group_name(conn, sg_id, vpc_id):
    name = None
    for sg in conn.get_all_security_groups(filters={'group-id':sg_id, 'vpc-id': vpc_id}):
        if sg.id == sg_id:
            name = sg.name
            return name
    raise Exception("could not resolve security group id '{0}' in VPC '{1}'".format(sg_id, vpc_id))
