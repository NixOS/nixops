import functools
import re
import string
from typing import Optional
from textwrap import dedent

__all__ = ["py2nix", "nix2py", "nixmerge", "expand_dict", "RawValue", "Function"]


class RawValue(object):
    def __init__(self, value):
        self.value = value

    def get_min_length(self):
        return len(self.value)

    def is_inlineable(self):
        return True

    def indent(self, level=0, inline=False, maxwidth=80):
        return "  " * level + self.value

    def __repr__(self):
        return self.value

    def __eq__(self, other):
        return isinstance(other, RawValue) and other.value == self.value


class MultiLineRawValue(RawValue):
    def __init__(self, values):
        self.values = values

    def get_min_length(self):
        return None

    def is_inlineable(self):
        return False

    def indent(self, level=0, inline=False, maxwidth=80):
        return "\n".join(["  " * level + value for value in self.values])


class Function(object):
    def __init__(self, head, body):
        self.head = head
        self.body = body

    def __repr__(self):
        return "{0} {1}".format(self.head, self.body)

    def __eq__(self, other):
        return (
            isinstance(other, Function)
            and other.head == self.head
            and other.body == self.body
        )


class Call(object):
    def __init__(self, fun, arg):
        self.fun = fun
        self.arg = arg

    def __repr__(self):
        return "{0} {1}".format(self.fun, self.arg)

    def __eq__(self, other):
        return (
            isinstance(other, Call) and other.fun == self.fun and other.arg == self.arg
        )


class Container(object):
    def __init__(self, prefix, children, suffix, inline_variant=None):
        self.prefix = prefix
        self.children = children
        self.suffix = suffix
        self.inline_variant = inline_variant

    def get_min_length(self):
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

    def is_inlineable(self):
        return all([child.is_inlineable() for child in self.children])

    def indent(self, level=0, inline=False, maxwidth=80):
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


def enclose_node(node, prefix="", suffix=""):
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


def _fold_string(value, rules):
    folder = lambda val, rule: val.replace(rule[0], rule[1])
    return functools.reduce(folder, rules, value)


def py2nix(value, initial_indentation=0, maxwidth=80, inline=False):
    """
    Return the given value as a Nix expression string.

    If initial_indentation is to a specific level (two spaces per level), don't
    inline fewer than that. Also, 'maxwidth' specifies the maximum line width
    which is enforced whenever it is possible to break an expression. Set to 0
    if you want to break on every occasion possible. If 'inline' is set to
    True, squash everything into a single line.
    """

    def _enc_int(node):
        if node < 0:
            return RawValue("builtins.sub 0 " + str(-node))
        else:
            return RawValue(str(node))

    def _enc_str(node, for_attribute=False):
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

    def _enc_list(nodes):
        if len(nodes) == 0:
            return RawValue("[]")
        pre, post = "[", "]"
        while len(nodes) == 1 and isinstance(nodes[0], list):
            nodes = nodes[0]
            pre, post = pre + " [", post + " ]"
        return Container(pre, [_enc(n, inlist=True) for n in nodes], post)

    def _enc_key(key):
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

    def _enc_attrset(node):
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

    def _enc_function(node):
        body = _enc(node.body)
        return enclose_node(body, node.head + ": ")

    def _enc_call(node):
        return Container("(", [_enc(node.fun), _enc(node.arg)], ")")

    def _enc(node, inlist=False):
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


def expand_dict(unexpanded):
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


def nixmerge(expr1, expr2):
    """
    Merge both expressions into one, merging dictionary keys and appending list
    elements if they otherwise would clash.
    """

    def _merge_dicts(d1, d2):
        out = {}
        for key in set(d1.keys()).union(d2.keys()):
            if key in d1 and key in d2:
                out[key] = _merge(d1[key], d2[key])
            elif key in d1:
                out[key] = d1[key]
            else:
                out[key] = d2[key]
        return out

    def _merge(e1, e2):
        if isinstance(e1, dict) and isinstance(e2, dict):
            return _merge_dicts(e1, e2)
        elif isinstance(e1, list) and isinstance(e2, list):
            l = []
            seen = set()
            for x in e1 + e2:
                if x not in seen:
                    seen.add(x)
                    l.append(x)
            return l
        else:
            err = "unable to merge {0} with {1}".format(type(e1), type(e2))
            raise ValueError(err)

    return _merge(expr1, expr2)


def nix2py(source):
    """
    Dedent the given Nix source code and encode it into multiple raw values
    which are used as-is and only indentation will take place.
    """
    return MultiLineRawValue(dedent(source).strip().splitlines())
