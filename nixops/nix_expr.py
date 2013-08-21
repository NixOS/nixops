import re
import string

from textwrap import dedent

__all__ = ['RawValue', 'Function', 'py2nix', 'nix2py', 'merge_dicts']


class RawValue(object):
    def __init__(self, value):
        self.value = value

    def get_min_length(self):
        return len(self.value)

    def indent(self, level=0, inline=False, maxwidth=80):
        return "  " * level + self.value


class Function(object):
    def __init__(self, head, body):
        self.head = head
        self.body = body


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


def enclose_node(node, prefix="", suffix=""):
    if isinstance(node, RawValue):
        return RawValue(prefix + node.value + suffix)
    else:
        if node.inline_variant is not None:
            new_inline = RawValue(prefix + node.inline_variant.value + suffix)
        else:
            new_inline = None
        return Container(prefix + node.prefix, node.children,
                         node.suffix + suffix, new_inline)


def _fold_string(value, rules):
    folder = lambda val, rule: val.replace(rule[0], rule[1])
    return reduce(folder, rules, value)


def py2nix(value, initial_indentation=0, maxwidth=80):
    """
    Return the given value as a Nix expression string.
    IF initial_indentation is to a specific level (two spaces per level), don't
    inline fewer than that. Also, 'maxwidth' specifies the maximum line width
    which is enforced whenever it is possible to break an expression. Set to 0
    if you want to break on every occasion possible.
    """
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

            nodes.append(enclose_node(contents, prefix, suffix))
        return Container("{", nodes, "}")

    def _enc_function(node):
        body = _enc(node.body)
        return enclose_node(body, node.head + ": ")

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
        elif isinstance(node, Function):
            return _enc_function(node)
        else:
            raise ValueError("Unable to encode {0}.".format(repr(node)))

    return _enc(value).indent(initial_indentation, maxwidth=maxwidth)


def merge_dicts(dict1, dict2):
    out = {}
    for key in set(dict1.keys()).union(dict2.keys()):
        if key in dict1 and key in dict2:
            out[key] = merge_dicts(dict1[key], dict2[key])
        elif key in dict1:
            out[key] = dict1[key]
        else:
            out[key] = dict2[key]
    return out


class ParseFailure(Exception):
    def __init__(self, pos, msg=None):
        self.pos = pos
        self.msg = msg

    def __str__(self):
        if self.msg is None:
            return "Parse error at position {0}".format(self.pos)
        else:
            return self.msg + " (pos: {0})".format(self.pos)


class ParseSuccess(object):
    def __init__(self, pos, data):
        self.pos = pos
        self.data = data


RE_STRING = re.compile(r"\"(.*?[^\\])\"|''(.*?[^'])''(?!\$\{|')", re.DOTALL)
RE_ATTR = re.compile(r'"(.*?(?![^\\]\\))"|([a-z_][a-z0-9_]*)', re.DOTALL)


def nix2py(source):
    maxpos = len(source)

    def _skip_whitespace(pos):
        while source[pos].isspace():
            pos += 1
        return pos

    def _parse_string(pos):
        match = RE_STRING.match(source, pos)
        if match is None:
            return ParseFailure(pos)

        if match.group(1):
            data = _fold_string(match.group(1), [
                (r'\"', '"'),
                (r'\n', "\n"),
                (r'\t', "\t"),
                (r'\${', "${"),
                ('\\\\', "\\"),
            ])
        else:
            data = _fold_string(dedent(match.group(2)), [
                ("'''", "''"),
                (r"'\n", "\n"),
                (r"'\t", "\t"),
                (r"''${", "${"),
            ]).lstrip('\n')
        return ParseSuccess(match.end(), data)

    def _parse_int(pos):
        mul = 1
        if source[pos:pos+15] == "builtins.sub 0 ":
            pos += 15
            mul = -1
        data = ""
        while pos < maxpos and source[pos].isdigit():
            data += source[pos]
            pos += 1
        if len(data) == 0:
            return ParseFailure(pos)
        else:
            return ParseSuccess(pos, int(data) * mul)

    def _parse_bool(pos):
        if source[pos:pos+4] == "true":
            return ParseSuccess(pos + 4, True)
        elif source[pos:pos+5] == "false":
            return ParseSuccess(pos + 5, False)
        else:
            return ParseFailure(pos)

    def _parse_null(pos):
        if source[pos:pos+4] == "null":
            return ParseSuccess(pos + 4, None)
        else:
            return ParseFailure(pos)

    def _parse_list(pos):
        items = []
        if source[pos] == '[':
            result = _parse_expr(pos + 1)
            while isinstance(result, ParseSuccess):
                items.append(result.data)
                result = _parse_expr(result.pos)
            newpos = _skip_whitespace(result.pos)
            if source[newpos] == ']':
                return ParseSuccess(newpos + 1, items)
            else:
                return result
        else:
            return ParseFailure(pos)

    def _parse_attr(pos):
        newpos = _skip_whitespace(pos)
        match = RE_ATTR.match(source, newpos)
        if match is None:
            return ParseFailure(newpos)
        if match.group(1):
            data = _fold_string(match.group(1), [
                (r'\"', '"'),
                ('\\\\', "\\"),
            ])
        else:
            data = match.group(2)
        return ParseSuccess(match.end(), data)

    def _parse_dotattr(pos):
        attrs = []
        attr = _parse_attr(pos)
        newpos = pos
        while isinstance(attr, ParseSuccess):
            attrs.append(attr)
            newpos = _skip_whitespace(attr.pos)
            if source[newpos] == '.':
                newpos += 1
            else:
                break
            attr = _parse_attr(newpos)
        if len(attrs) == 0:
            return ParseFailure(newpos)
        return ParseSuccess(attrs[-1].pos, [attr.data for attr in attrs])

    def _parse_keyval(pos):
        key = _parse_dotattr(pos + 1)
        if not isinstance(key, ParseSuccess):
            return key
        newpos = _skip_whitespace(key.pos)
        if source[newpos] != '=':
            return ParseFailure(newpos)
        newpos += 1
        value = _parse_expr(newpos)
        if not isinstance(value, ParseSuccess):
            return value
        newpos = _skip_whitespace(value.pos)
        if source[newpos] != ';':
            return ParseFailure(newpos)
        return ParseSuccess(newpos + 1, (key.data, value.data))

    def _reduce_keys(keys, value):
        if len(keys) == 0:
            return value
        else:
            return {keys[0]: _reduce_keys(keys[1:], value)}

    def _postprocess_attrlist(attrs):
        dictlist = []
        for keys, value in attrs:
            dictlist.append({keys[0]: _reduce_keys(keys[1:], value)})
        return reduce(merge_dicts, dictlist)

    def _parse_attrset(pos):
        attrs = []
        if source[pos] == '{':
            keyval = _parse_keyval(pos + 1)
            newpos = keyval.pos
            while isinstance(keyval, ParseSuccess):
                attrs.append(keyval.data)
                newpos = keyval.pos
                keyval = _parse_keyval(newpos)

            newpos = _skip_whitespace(newpos)

            if source[newpos] == '}':
                return ParseSuccess(newpos + 1, _postprocess_attrlist(attrs))
            else:
                return ParseFailure(newpos)
        else:
            return ParseFailure(pos)

    def _parse_expr(pos):
        newpos = _skip_whitespace(pos)
        for parser in [_parse_string, _parse_int, _parse_bool, _parse_null,
                       _parse_list, _parse_attrset]:
            result = parser(newpos)
            if isinstance(result, ParseSuccess):
                return result
        return ParseFailure(newpos)

    result = _parse_expr(0)
    if isinstance(result, ParseSuccess):
        return result.data
    else:
        raise result
