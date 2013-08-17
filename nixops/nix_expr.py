import string

__all__ = ['RawValue', 'py2nix']


class RawValue(object):
    def __init__(self, value):
        self.value = value

    def get_min_length(self):
        return len(self.value)

    def indent(self, level=0, inline=False, maxwidth=80):
        return "  " * level + self.value


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
        return (len(self.prefix) + len(self.suffix) + 1 + len(self.children) +
                sum([child.get_min_length() for child in self.children]))

    def indent(self, level=0, inline=False, maxwidth=80):
        if level * 2 + self.get_min_length() < maxwidth:
            inline = True
        ind = "  " * level
        if inline and self.inline_variant is not None:
            return self.inline_variant.indent(level=level, inline=True,
                                              maxwidth=maxwidth)
        elif inline:
            sep = ' '
            lines = ' '.join([child.indent(level=0, inline=True)
                              for child in self.children])
            suffix_ind = ""
        else:
            sep = '\n'
            lines = '\n'.join([child.indent(level + 1, inline=inline,
                                            maxwidth=maxwidth)
                               for child in self.children])
            suffix_ind = ind
        return ind + self.prefix + sep + lines + sep + suffix_ind + self.suffix


def py2nix(value, initial_indentation=0, maxwidth=80):
    """
    Return the given value as a Nix expression string.
    IF initial_indentation is to a specific level (two spaces per level), don't
    inline fewer than that. Also, 'maxwidth' specifies the maximum line width
    which is enforced whenever it is possible to break an expression. Set to 0
    if you want to break on every occasion possible.
    """
    def _fold_string(value, rules):
        folder = lambda val, rule: val.replace(rule[0], rule[1])
        return reduce(folder, rules, value)

    def _enc_int(node):
        if node < 0:
            return RawValue("builtins.sub 0 " + str(-node))
        else:
            return RawValue(str(node))

    def _enc_str(node, for_attribute=False):
        encoded = _fold_string(node, [
            ("\\", "\\\\"),
            ("${", "\\${"),
            ('"', '\\"'),
            ("\n", "\\n"),
            ("\t", "\\t"),
        ])

        inline_variant = RawValue('"{0}"'.format(encoded))

        if for_attribute:
            return inline_variant.value

        if node.endswith("\n"):
            encoded = _fold_string(node[:-1], [
                ("''", "'''"),
                ("${", "''${"),
                ("\t", "'\\t"),
            ])

            atoms = [RawValue(line) for line in encoded.splitlines()]
            return Container("''", atoms, "''", inline_variant=inline_variant)
        else:
            return inline_variant

    def _enc_list(node):
        pre, post = "[", "]"
        while len(node) == 1 and isinstance(node[0], list):
            node = node[0]
            pre, post = pre + " [", post + " ]"
        return Container(pre, map(_enc, node), post)

    def _enc_key(key):
        if not isinstance(key, basestring):
            raise KeyError("Key {0} is not a string.".format(repr(key)))
        elif len(key) == 0:
            raise KeyError("Key name has zero length.")

        if all(char in string.letters + string.digits + '_'
               for char in key) and not key[0].isdigit():
            return key
        else:
            return _enc_str(key, for_attribute=True)

    def _enc_attrset(node):
        nodes = []
        for key, value in sorted(node.items()):
            encoded_key = _enc_key(key)

            # If the children are attrsets as well and only contain one
            # attribute, recursively merge them with a dot, like "a.b.c".
            child_key, child_value = key, value
            while isinstance(child_value, dict) and len(child_value) == 1:
                child_key, child_value = child_value.items()[0]
                encoded_key += "." + child_key

            contents = _enc(child_value)
            prefix = "{0} = ".format(encoded_key)
            suffix = ";"

            if isinstance(contents, RawValue):
                node = RawValue(prefix + contents.value + suffix)
            else:
                if contents.inline_variant is not None:
                    new_inline = RawValue(
                        prefix + contents.inline_variant.value + suffix
                    )
                else:
                    new_inline = None
                node = Container(prefix + contents.prefix, contents.children,
                                 contents.suffix + suffix, new_inline)
            nodes.append(node)
        return Container("{", nodes, "}")

    def _enc(node):
        if isinstance(node, RawValue):
            return node
        elif node is True:
            return RawValue("true")
        elif node is False:
            return RawValue("false")
        elif node is None:
            return RawValue("null")
        elif isinstance(node, (int, long)):
            return _enc_int(node)
        elif isinstance(node, basestring):
            return _enc_str(node)
        elif isinstance(node, list):
            return _enc_list(node)
        elif isinstance(node, dict):
            return _enc_attrset(node)
        else:
            raise ValueError("Unable to encode {0}.".format(repr(node)))

    return _enc(value).indent(initial_indentation, maxwidth=maxwidth)
