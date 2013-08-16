import re

__all__ = ['py2nix']


class Atom(object):
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
        if self.get_min_length() < maxwidth:
            inline = True
        if inline and self.inline_variant is not None:
            return self.inline_variant.indent(level=level, inline=True)
        elif inline:
            sep = ' '
            lines = ' '.join([child.indent(level=0, inline=True)
                              for child in self.children])
        else:
            sep = '\n'
            lines = '\n'.join([child.indent(level + 1)
                               for child in self.children])
        return self.prefix + sep + lines + sep + "  " * level + self.suffix


def py2nix(value, initial_indentation=0, maxwidth=80):
    """
    Return the given value as a Nix expression string.
    """
    def _fold_string(value, rules):
        folder = lambda val, rule: val.replace(rule[0], rule[1])
        return reduce(folder, rules, value)

    def _enc_int(node):
        if node < 0:
            return Atom("builtins.sub 0 " + str(-node))
        else:
            return Atom(str(node))

    def _enc_str(node):
        encoded = _fold_string(node, [
            ("\\", "\\\\"),
            ("${", "\\${"),
            ('"', '\\"'),
            ("\n", "\\n"),
            ("\t", "\\t"),
        ])
        inline_variant = Atom('"{0}"'.format(encoded))

        if node.endswith("\n"):
            encoded = _fold_string(node[:-1], [
                ("''", "'''"),
                ("${", "''${"),
                ("\t", "'\\t"),
            ])

            atoms = [Atom(line) for line in encoded.splitlines()]
            return Container("''", atoms, "''", inline_variant=inline_variant)
        else:
            return inline_variant

    def _enc_list(node):
        return Container("[", map(_enc, node), "]")

    def _enc(node):
        if node is True:
            return Atom("true")
        elif node is False:
            return Atom("false")
        elif node is None:
            return Atom("null")
        elif isinstance(node, (int, long)):
            return _enc_int(node)
        elif isinstance(node, str):
            return _enc_str(node)
        elif isinstance(node, list):
            return _enc_list(node)
        else:
            raise ValueError("Unable to encode {0}.".format(repr(node)))

    return _enc(value).indent(initial_indentation, maxwidth=maxwidth)
