/*
Expect a reasonable error message when the `network.lock` attribute
has a value of the wrong type
*/
{
  network.storage.memory = {};
  network.lock = "meh";
}
