{
  network = rec {
    storage.s3 = {
      bucket = "hi";
      whatever = "there";
    };

    lock.s3 = storage.s3 // {
      dynamodb_table = "blah";
    };
  };
}
