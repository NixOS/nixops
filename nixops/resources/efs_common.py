import boto3
import nixops.ec2_utils

class EFSCommonState():

    _client = None

    def _get_client(self, access_key_id=None, region=None):
        if self._client: return self._client

        creds = nixops.ec2_utils.fetch_aws_secret_key(access_key_id or self.access_key_id)

        self._client = boto3.session.Session().client('efs',
                                                      region_name=region or self.region,
                                                      **creds)

        return self._client
