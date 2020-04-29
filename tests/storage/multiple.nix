/*
Users should get a reasonable error messages if they accidentally
specify multiple storage backends
*/
{
  network = rec {
    storage.s3 = {
      bucket = "hi";
      whatever = "there";
    };

    storage.legacy = {};
  };
}
