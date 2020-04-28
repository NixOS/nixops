/*
Expect a reasonable error message when the `network` attribute
has an empty attributeset for network.

2020-04-28 User gets a not terrible message:

  TypeError: type of storage must be collections.abc.Mapping;
             got NoneType instead

and we're going to punt on this error handling from here, since we
have now reached a point where ImmutableValidatedObject handles
errors.
*/
{
  network = {};
}
