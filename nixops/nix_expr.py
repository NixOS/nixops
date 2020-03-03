import functools
import re
import string
from typing import Any, Dict, List, Optional, Sequence, Tuple, TypeVar, Union, overload
from textwrap import dedent

import sys

if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal

__all__ = ["py2nix", "nix2py", "nixmerge", "expand_dict", "RawValue", "Function"]

Node = Union["MultiLineRawValue", "RawValue", "Container"]


class RawValue(object):
    def __init__(self, value: Any) -> None:
        self.value = value

    def get_min_length(self) -> int:
        return len(self.value)

    def is_inlineable(self) -> bool:
        return True

    def indent(self, level: int = 0, inline: bool = False, maxwidth: int = 80) -> str:
        return "  " * level + self.value

    def __repr__(self) -> str:
        return self.value

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, RawValue) and other.value == self.value


# TODO: why does MultiLineRawValue inherit RawValue but not use self.value?
class MultiLineRawValue(RawValue):
    def __init__(self, values: List[Any]) -> None:
        self.values = values

    def get_min_length(self) -> int:
        return 0

    def is_inlineable(self) -> bool:
        return False

    def indent(self, level: int = 0, inline: bool = False, maxwidth: int = 80) -> str:
        return "\n".join(["  " * level + value for value in self.values])

    # TODO: is this correct?
    def __repr__(self) -> str:
        return str(self.values)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, MultiLineRawValue) and other.values == self.values


class Function(object):
    def __init__(self, head: str, body: Union[str, Dict[Any, Any]]) -> None:
        self.head = head
        self.body = body

    def __repr__(self) -> str:
        return "{0} {1}".format(self.head, self.body)

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, Function)
            and other.head == self.head
            and other.body == self.body
        )


class Call(object):
    def __init__(self, fun: RawValue, arg: Any) -> None:
        self.fun = fun
        self.arg = arg

    def __repr__(self) -> str:
        return "{0} {1}".format(self.fun, self.arg)

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, Call) and other.fun == self.fun and other.arg == self.arg
        )


class Container(object):
    def __init__(
        self,
        prefix: str,
        children: Sequence[Node],
        suffix: str,
        inline_variant: Optional[Any] = None,
    ) -> None:
        self.prefix = prefix
        self.children = children
        self.suffix = suffix
        self.inline_variant = inline_variant

    def get_min_length(self) -> int:
        """
        Return the minimum length of this container and all sub-containers.
        """
        return (
            len(self.prefix)
            + len(self.suffix)
            + 1
            + len(self.children)
            + sum([child.get_min_length() for child in self.children])
        )

    def is_inlineable(self) -> bool:
        return all([child.is_inlineable() for child in self.children])

    def indent(self, level: int = 0, inline: bool = False, maxwidth: int = 80) -> str:
        if not self.is_inlineable():
            inline = False
        elif level * 2 + self.get_min_length() < maxwidth:
            inline = True
        ind = "  " * level
        if inline and self.inline_variant is not None:
            return self.inline_variant.indent(
                level=level, inline=True, maxwidth=maxwidth
            )
        elif inline:
            sep = " "
            lines = " ".join(
                [child.indent(level=0, inline=True) for child in self.children]
            )
            suffix_ind = ""
        else:
            sep = "\n"
            lines = "\n".join(
                [
                    child.indent(level + 1, inline=inline, maxwidth=maxwidth)
                    for child in self.children
                ]
            )
            suffix_ind = ind
        return ind + self.prefix + sep + lines + sep + suffix_ind + self.suffix


def enclose_node(node: Node, prefix: str = "", suffix: str = "",) -> Node:
    if isinstance(node, MultiLineRawValue):
        new_values = list(node.values)
        new_values[0] = prefix + new_values[0]
        new_values[-1] += suffix
        return MultiLineRawValue(new_values)
    elif isinstance(node, RawValue):
        return RawValue(prefix + node.value + suffix)
    else:
        new_inline: Optional[RawValue]
        if node.inline_variant is not None:
            new_inline = RawValue(prefix + node.inline_variant.value + suffix)
        else:
            new_inline = None
        return Container(
            prefix + node.prefix, node.children, node.suffix + suffix, new_inline
        )


def _fold_string(value: str, rules: List[Tuple[str, str]]) -> str:
    folder = lambda val, rule: val.replace(rule[0], rule[1])
    return functools.reduce(folder, rules, value)


def py2nix(
    value: Any, initial_indentation: int = 0, maxwidth: int = 80, inline: bool = False
) -> str:
    """
    Return the given value as a Nix expression string.

    If initial_indentation is to a specific level (two spaces per level), don't
    inline fewer than that. Also, 'maxwidth' specifies the maximum line width
    which is enforced whenever it is possible to break an expression. Set to 0
    if you want to break on every occasion possible. If 'inline' is set to
    True, squash everything into a single line.
    """

    def _enc_int(node: int) -> RawValue:
        if node < 0:
            return RawValue("builtins.sub 0 " + str(-node))
        else:
            return RawValue(str(node))

    @overload
    def _enc_str(node: str, for_attribute: Literal[True]) -> str:
        ...

    @overload
    def _enc_str(
        node: str, for_attribute: Literal[False]
    ) -> Union[RawValue, Container]:
        ...

    @overload
    def _enc_str(node: str) -> Union[RawValue, Container]:
        ...

    def _enc_str(
        node: str, for_attribute: bool = False
    ) -> Union[str, RawValue, Container]:
        encoded = _fold_string(
            node,
            [
                ("\\", "\\\\"),
                ("${", "\\${"),
                ('"', '\\"'),
                ("\n", "\\n"),
                ("\t", "\\t"),
            ],
        )

        inline_variant = RawValue('"{0}"'.format(encoded))

        if for_attribute:
            return inline_variant.value

        if node.endswith("\n"):
            encoded = _fold_string(
                node[:-1], [("''", "'''"), ("${", "''${"), ("\t", "'\\t"),]
            )

            atoms = [RawValue(line) for line in encoded.splitlines()]
            return Container("''", atoms, "''", inline_variant=inline_variant)
        else:
            return inline_variant

    def _enc_list(nodes: List[Any]) -> Union[RawValue, Container]:
        if len(nodes) == 0:
            return RawValue("[]")
        pre, post = "[", "]"
        while len(nodes) == 1 and isinstance(nodes[0], list):
            nodes = nodes[0]
            pre, post = pre + " [", post + " ]"
        return Container(pre, [_enc(n, inlist=True) for n in nodes], post)

    def _enc_key(key: str) -> str:
        if not isinstance(key, str):
            raise KeyError("key {0} is not a string".format(repr(key)))
        elif len(key) == 0:
            raise KeyError("key name has zero length")

        if (
            all(char in string.ascii_letters + string.digits + "_" for char in key)
            and not key[0].isdigit()
        ):
            return key
        else:
            return _enc_str(key, for_attribute=True)

    def _enc_attrset(node: Dict[Any, Any]) -> Union[RawValue, Container]:
        if len(node) == 0:
            return RawValue("{}")
        nodes = []
        for key, value in sorted(node.items()):
            encoded_key = _enc_key(key)

            # If the children are attrsets as well and only contain one
            # attribute, recursively merge them with a dot, like "a.b.c".
            child_key, child_value = key, value
            while isinstance(child_value, dict) and len(child_value) == 1:
                child_key, child_value = next(iter(child_value.items()))
                encoded_key += "." + _enc_key(child_key)

            contents = _enc(child_value)
            prefix = "{0} = ".format(encoded_key)
            suffix = ";"

            nodes.append(enclose_node(contents, prefix, suffix))
        return Container("{", nodes, "}")

    def _enc_function(node: Function) -> Union[RawValue, MultiLineRawValue, Container]:
        body = _enc(node.body)
        return enclose_node(body, node.head + ": ")

    def _enc_call(node: Call) -> Container:
        return Container("(", [_enc(node.fun), _enc(node.arg)], ")")

    def _enc(node: Any, inlist: bool = False) -> Node:
        if isinstance(node, RawValue):
            if inlist and (
                isinstance(node, MultiLineRawValue)
                or any(char.isspace() for char in node.value)
            ):
                return enclose_node(node, "(", ")")
            else:
                return node
        elif node is True:
            return RawValue("true")
        elif node is False:
            return RawValue("false")
        elif node is None:
            return RawValue("null")
        elif isinstance(node, int):
            return _enc_int(node)
        elif isinstance(node, str):
            return _enc_str(node)
        elif isinstance(node, list):
            return _enc_list(node)
        elif isinstance(node, dict):
            return _enc_attrset(expand_dict(node))
        elif isinstance(node, Function):
            if inlist:
                return enclose_node(_enc_function(node), "(", ")")
            else:
                return _enc_function(node)
        elif isinstance(node, Call):
            if inlist:
                return enclose_node(_enc_call(node), "(", ")")
            else:
                return _enc_call(node)
        else:
            raise ValueError("unable to encode {0}".format(repr(node)))

    return _enc(value).indent(initial_indentation, maxwidth=maxwidth, inline=inline)


def expand_dict(unexpanded: Dict[Any, Any]) -> Dict[Any, Any]:
    """
    Turns a dict containing tuples as keys into a set of nested dictionaries.

    Examples:

    >>> expand_dict({('a', 'b', 'c'): 'd'})
    {'a': {'b': {'c': 'd'}}}
    >>> expand_dict({('a', 'b'): 'c',
    ...               'a': {('d', 'e'): 'f'}})
    {'a': {'b': 'c', 'd': {'e': 'f'}}}
    """
    paths, strings = [], {}
    for key, val in unexpanded.items():
        if isinstance(key, tuple):
            if len(key) == 0:
                raise KeyError("invalid key {0}".format(repr(key)))

            newkey = key[0]
            if len(key) > 1:
                newval = {key[1:]: val}
            else:
                newval = val
            paths.append({newkey: newval})
        else:
            strings[key] = val

    return {
        key: (expand_dict(val) if isinstance(val, dict) else val)
        for key, val in functools.reduce(nixmerge, paths + [strings]).items()
    }


ExprT = TypeVar("ExprT")


def nixmerge(expr1: ExprT, expr2: ExprT) -> ExprT:
    """
    Merge both expressions into one, merging dictionary keys and appending list
    elements if they otherwise would clash.
    """

    def _merge_dicts(d1: Dict[Any, Any], d2: Dict[Any, Any]) -> Dict[Any, Any]:
        out = {}
        for key in set(d1.keys()).union(d2.keys()):
            if key in d1 and key in d2:
                out[key] = _merge(d1[key], d2[key])
            elif key in d1:
                out[key] = d1[key]
            else:
                out[key] = d2[key]
        return out

    def _merge(e1: Any, e2: Any) -> Any:
        if isinstance(e1, dict) and isinstance(e2, dict):
            return _merge_dicts(e1, e2)
        elif isinstance(e1, list) and isinstance(e2, list):
            return list(set(e1).union(e2))
        else:
            err = "unable to merge {0} with {1}".format(type(e1), type(e2))
            raise ValueError(err)

    return _merge(expr1, expr2)


def nix2py(source: str) -> MultiLineRawValue:
    """
    Dedent the given Nix source code and encode it into multiple raw values
    which are used as-is and only indentation will take place.
    """
    return MultiLineRawValue(dedent(source).strip().splitlines())
