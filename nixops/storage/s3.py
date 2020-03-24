from __future__ import annotations
from nixops.storage import StorageArgDescriptions, StorageArgValues
import boto3
from botocore.exceptions import ClientError
import sys
import os
import typing
from typing import Dict

if typing.TYPE_CHECKING:
    import nixops.statefile


class S3Backend:
    @staticmethod
    def arguments() -> StorageArgDescriptions:
        raise NotImplementedError

    def __init__(self, args: StorageArgValues) -> None:
        self.bucket = args["bucket"]
        self.key = args["key"]
        self.region = args["region"]
        self.profile = args["profile"]
        self.dynamodb_table = args["dynamodb_table"]
        self.s3_endpoint = args.get("s3_endpoint")
        self.kms_keyid = args.get("kms_keyid")
        self.aws = boto3.Session(region_name=self.region, profile_name=self.profile)

    # fetchToFile: acquire a lock and download the state file to
    # the local disk. Note: no arguments will be passed over kwargs.
    # Making it part of the type definition allows adding new
    # arguments later.
    def fetchToFile(self, path: str, **kwargs) -> None:
        self.lock(path)
        try:
            with open(path, "wb") as f:
                self.aws.client("s3").download_fileobj(self.bucket, self.key, f)
            print("Fetched!")
        except ClientError as e:
            from pprint import pprint

            pprint(e)
            if e.response["Error"]["Code"] == "404":
                self.aws.client("s3").put_object(
                    Bucket=self.bucket, Key=self.key, Body=b"", **self.encargs()
                )

    def onOpen(self, sf: nixops.statefile.StateFile, **kwargs) -> None:
        pass

    # uploadFromFile: upload the new state file and release any locks
    # Note: no arguments will be passed over kwargs. Making it part of
    # the type definition allows adding new arguments later.
    def uploadFromFile(self, path: str, **kwargs) -> None:
        with open(path, "rb") as f:
            self.aws.client("s3").upload_fileobj(
                f, self.bucket, self.key, ExtraArgs=self.encargs()
            )

        self.unlock(path)

    def s3(self) -> None:
        self.aws.client("s3", endpoint_url=self.s3_endpoint)

    def encargs(self) -> Dict[str, str]:
        if self.kms_keyid is not None:
            return {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": self.kms_keyid}
        else:
            return {}

    def lock(self, path) -> None:
        r = self.aws.client("dynamodb").put_item(
            TableName=self.dynamodb_table,
            Item={"LockID": {"S": f"{self.bucket}/{self.key}"},},
            ConditionExpression="attribute_not_exists(LockID)",
        )

    def unlock(self, path: str) -> None:
        self.aws.client("dynamodb").delete_item(
            TableName=self.dynamodb_table,
            Key={"LockID": {"S": f"{self.bucket}/{self.key}"},},
        )
