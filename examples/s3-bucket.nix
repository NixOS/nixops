{ region ? "us-east-1"
, accessKeyId ? "DOVAH..."
, ...
}:
{
  resources.s3Buckets.s3-test-bucket =
    {
      inherit region accessKeyId;
      name = "s3-test-bucket";
      versioning = "Suspended";
      policy = ''
        {
          "Version": "2012-10-17",
          "Statement": [
            {
              "Sid": "testing",
              "Effect": "Allow",
              "Principal": "*",
              "Action": "s3:GetObject",
              "Resource": "arn:aws:s3:::s3-test-bucket/*"
            }
          ]
        }
        '';
       lifeCycle = ''
         {
           "Rules": [
              {
                "Status": "Enabled",
                "Prefix": "",
                "Transitions": [
                  {
                    "Days": 30,
                    "StorageClass": "GLACIER"
                  }
                ],
                "ID": "Glacier",
                "AbortIncompleteMultipartUpload":
                  {
                    "DaysAfterInitiation": 7
                  }
              }
           ]
         }
       '';
    };
}
