{
  machine.deployment = {
    storeKeysOnMachine = false;

    keys."elsewhere.key".text = "12345";
    keys."elsewhere.key".destinationFolder = /new/directory;
  };
}
