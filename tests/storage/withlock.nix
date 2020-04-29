{
  network = rec {
    storage.s3 = {
      bucket = "hi";
      whatever = "there";
    };

    locking.s3 = storage.s3 // {
      dynamodb_table = "blah";
    };
  };
}
