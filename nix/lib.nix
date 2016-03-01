lib:

with lib;

{

  resource = type: mkOptionType {
    name = "resource of type ‘${type}’";
    typerep = "(resourceOf${type.typerep})";
    check = x: x._type or "" == type;
    merge = mergeOneOption;
  };

  shorten_uuid = uuid: replaceChars ["-"] [""] uuid;

}
