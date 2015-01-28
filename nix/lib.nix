lib:

with lib;

{

  resource = type: mkOptionType {
    name = "resource of type ‘${type}’";
    check = x: x._type or "" == type;
    merge = mergeOneOption;
  };

  shorten_uuid = uuid: replaceChars ["-"] [""] uuid;

}
