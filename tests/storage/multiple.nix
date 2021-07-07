/*
Users should get a reasonable error messages if they accidentally
specify multiple storage backends
*/
{
  network = rec {
    storage.memory = {};
    storage.legacy = {};
  };
}
