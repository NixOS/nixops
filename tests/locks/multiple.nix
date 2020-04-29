/*
Users should get a reasonable error messages if they accidentally
specify multiple lock backends
*/
{
  network = {
    storage.memory = {};
    lock.legacy = {};
    lock.noop = {};
  };
}
