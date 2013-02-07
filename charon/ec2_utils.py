# -*- coding: utf-8 -*-

import os
import boto.ec2
import time                                                                                    
import random                                                                                  

from boto.exception import EC2ResponseError

def fetch_aws_secret_key(access_key_id):
    """Fetch the secret access key corresponding to the given access key ID from the environment or from ~/.ec2-keys"""
    secret_access_key = os.environ.get('EC2_SECRET_KEY') or os.environ.get('AWS_SECRET_ACCESS_KEY')
    path = os.path.expanduser("~/.ec2-keys")
    if os.path.isfile(path):
        f = open(path, 'r')
        contents = f.read()
        f.close()
        for l in contents.splitlines():
            l = l.split("#")[0] # drop comments
            w = l.split()
            if len(w) < 2 or len(w) > 3: continue
            if len(w) == 3 and w[2] == access_key_id:
                access_key_id = w[0]
                secret_access_key = w[1]
                break
            if w[0] == access_key_id:
                secret_access_key = w[1]
                break

    if not secret_access_key:
        raise Exception("please set $EC2_SECRET_KEY or $AWS_SECRET_ACCESS_KEY, or add the key for ‘{0}’ to ~/.ec2-keys"
                        .format(access_key_id))

    return (access_key_id, secret_access_key)


def connect(region, access_key_id):
    """Connect to the specified EC2 region using the given access key."""
    assert region
    (access_key_id, secret_access_key) = fetch_aws_secret_key(access_key_id)
    return boto.ec2.connect_to_region(
        region_name=region, aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)


def get_access_key_id():
    return os.environ.get('EC2_ACCESS_KEY') or os.environ.get('AWS_ACCESS_KEY_ID')


def retry(f, error_codes=[]):                                                                  
    i = 0                                                                                      
    num_retries = 6                                                                            
    while i <= num_retries:
        print i
        next_sleep = random.random() * (2 ** i)
        i += 1

        try:
            return f()
        except EC2ResponseError as e:
            if i == num_retries or not e.error_code in error_codes:
                raise e
        except Exception as e:
            raise e

        time.sleep(next_sleep)
