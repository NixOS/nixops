import unittest

from textwrap import dedent

from nixops.nix_expr import py2nix, nix2py, RawValue, Function, nixmerge

__all__ = ['Py2NixTest', 'Nix2PyTest']


class Py2NixTestBase(object):
    def test_numeric(self):
        self.assert_nix(123, "123")
        self.assert_nix(-123, "builtins.sub 0 123")
        self.assertRaises(ValueError, py2nix, 123.4)

    def test_boolean(self):
        self.assert_nix(True, "true")
        self.assert_nix(False, "false")

    def test_null(self):
        self.assert_nix(None, "null")

    def test_invalid(self):
        self.assertRaises(ValueError, py2nix, lambda: 123)
        self.assertRaises(ValueError, py2nix, Exception)

    def test_string(self):
        self.assert_nix("xyz", '"xyz"')
        self.assert_nix("a'b\"c", r'''"a'b\"c"''')
        self.assert_nix("abc\ndef\nghi", r'"abc\ndef\nghi"')
        self.assert_nix("abc\ndef\nghi\n", "''\n  abc\n  def\n  ghi\n''",
                        maxwidth=0)
        self.assert_nix("\\foo", r'"\\foo"')
        self.assert_nix("xx${yy}zz", r'"xx\${yy}zz"')
        self.assert_nix("xx\n${yy}\nzz\n", "''\n  xx\n  ''${yy}\n  zz\n''",
                        maxwidth=0)
        self.assert_nix("xx\n''yy\nzz\n", "''\n  xx\n  '''yy\n  zz\n''",
                        maxwidth=0)

    def test_raw_value(self):
        self.assert_nix({'a': RawValue('import <something>')},
                        '{ a = import <something>; }')
        self.assert_nix([RawValue("!")], '[ ! ]')

    def test_list(self):
        self.assert_nix([1, 2, 3], '[ 1 2 3 ]')
        self.assert_nix(["a", "b", "c"], '[ "a" "b" "c" ]')
        self.assert_nix(["a\na\na\n", "b\nb\n", "c"],
                        r'[ "a\na\na\n" "b\nb\n" "c" ]')
        self.assert_nix(["a\na\na\n", "b\nb\n", "c"],
                        '[\n  "a\\na\\na\\n"\n  "b\\nb\\n"\n  "c"\n]',
                        maxwidth=15)

    def test_nested_list(self):
        match = dedent('''
        [
          [ 1 2 3 ]
          [ 4 5 6 ]
          [
            [
              6
              6
              6
            ]
            [
              [
                7
                7
                7
              ]
              [
                8
                8
                8
              ]
              [
                9
                9
                9
              ]
            ]
          ]
        ]
        ''').strip()

        self.assert_nix([
            [1, 2, 3],
            [4, 5, 6],
            [[6, 6, 6], [[7, 7, 7], [8, 8, 8], [9, 9, 9]]]
        ], match, maxwidth=12)

    def test_nested_singletons(self):
        match = dedent('''
        [ [ [
          1
          2
          [ [ 3 ] ]
        ] ] ]
        ''').strip()

        self.assert_nix([[[1, 2, [[3]]]]], match, maxwidth=12)

    def test_attrkeys(self):
        self.assert_nix({'aAa': 123}, '{ aAa = 123; }')
        self.assert_nix({'a.a': 123}, '{ "a.a" = 123; }')
        self.assert_nix({'\\': 123}, r'{ "\\" = 123; }')
        self.assert_nix({'a1': 123}, '{ a1 = 123; }')
        self.assert_nix({'1a': 123}, '{ "1a" = 123; }')
        self.assert_nix({'_aA': 123}, '{ _aA = 123; }')
        self.assertRaises(KeyError, py2nix, {'': 123})
        self.assertRaises(KeyError, py2nix, {123: 123})

    def test_attrvalues(self):
        self.assert_nix({'a': "abc"}, '{ a = "abc"; }')
        self.assert_nix({'a': "a\nb\nc\n"}, r'{ a = "a\nb\nc\n"; }')
        self.assert_nix({'A': [1, 2, 3]}, r'{ A = [ 1 2 3 ]; }')

    def test_nested_attrsets(self):
        match = dedent('''
        {
          aaa = {
            bbb.ccc = 123;
            cCc = 456;
          };
          xxx = [
            1
            2
            3
          ];
          yyy.y1.y2.y3 = [
            "a"
            "b"
            {
              c = "d";
            }
          ];
        }
        ''').strip()

        self.assert_nix({
            'aaa': {
                'bbb': {
                    'ccc': 123,
                },
                'cCc': 456,
            },
            'xxx': [1, 2, 3],
            'yyy': {
                'y1': {'y2': {'y3': ["a", "b", {'c': 'd'}]}},
            },
        }, match, maxwidth=0)

    def test_functions(self):
        self.assert_nix(Function("Aaa", RawValue("bbb")),
                        "Aaa: bbb")
        self.assert_nix(Function("{ ... }", [1, 2, 3]),
                        "{ ... }: [ 1 2 3 ]")
        self.assert_nix(Function("{ ... }", "a\nb\nc\n"),
                        r'{ ... }: "a\nb\nc\n"')
        self.assert_nix(Function("{ ... }", "a\nb\nc\n"),
                        "{ ... }: ''\n  a\n  b\n  c\n''", maxwidth=0)
        self.assert_nix(Function("xxx", {'a': {'b': 'c'}}),
                        'xxx: {\n  a.b = "c";\n}', maxwidth=0)

    def test_nested_functions(self):
        match = dedent('''
        { config, pkgs, ... }: {
          a.b.c = 1;
          b.c.d = 2;
          d.e = [ "e" "f" ];
          e = f: {
            x = ''
              aaa
              bbb
              ccc
            '';
          };
        }
        ''').strip()

        self.assert_nix(Function(
            "{ config, pkgs, ... }",
            {'a': {'b': {'c': 1}},
             'b': {'c': {'d': 2}},
             'd': {'e': ['e', 'f']},
             'e': Function('f', {
                 'x': "aaa\nbbb\nccc\n"
             })}
        ), match, maxwidth=26)


class Py2NixTest(unittest.TestCase, Py2NixTestBase):
    def assert_nix(self, nix_expr, expected, maxwidth=80):
        result = py2nix(nix_expr, maxwidth=maxwidth)
        self.assertEqual(
            result, expected,
            "Expected:\n{0}\nGot:\n{1}".format(expected, result)
        )

    def test_function_call(self):
        self.assert_nix(Function("fun_call", {'a': 'b'}, call=True),
                        'fun_call { a = "b"; }')
        self.assert_nix(Function("multiline_call", {'a': 'b'}, call=True),
                        'multiline_call {\n  a = "b";\n}', maxwidth=0)


class Nix2PyTest(unittest.TestCase, Py2NixTestBase):
    def assert_nix(self, expected, source, maxwidth=80):
        self.assertEqual(nix2py(source), expected)


class NixMergeTest(unittest.TestCase):
    def assert_merge(self, sources, expect):
        self.assertEqual(reduce(nixmerge, sources), expect)

    def test_merge_list(self):
        self.assert_merge([
            [1, 2, 3],
            [4, 5, 6],
            [7, 6, 5],
            ["abc", "def"],
            ["ghi", "abc"],
        ], [1, 2, 3, 4, 5, 6, 7, "abc", "ghi", "def"])

    def test_merge_dict(self):
        self.assert_merge([
            {},
            {'a': {'b': {'c': 'd'}}},
            {'a': {'c': 'e'}},
            {'b': {'a': ['a']}},
            {'b': {'a': ['b']}},
            {'b': {'A': ['B']}},
            {'e': 'f'},
            {},
        ], {
            'a': {
                'c': 'e',
                'b': {'c': 'd'}
            },
            'b': {'a': ['a', 'b'],
                  'A': ['B']},
            'e': 'f',
        })

    def test_unhashable(self):
        self.assertRaises(TypeError, nixmerge, [[1]], [[2]])
        self.assertRaises(TypeError, nixmerge, [{'x': 1}], [{'y': 2}])

    def test_invalid(self):
        self.assertRaises(ValueError, nixmerge, [123], {'a': 456})
        self.assertRaises(ValueError, nixmerge, "a", "b")
        self.assertRaises(ValueError, nixmerge, 123, 456)
        self.assertRaises(ValueError, nixmerge, RawValue("a"), RawValue("b"))
        self.assertRaises(ValueError, nixmerge,
                          Function("aaa", {'a': 1}), Function("ccc", {'b': 2}))
        self.assertRaises(ValueError, nixmerge,
                          Function("aaa", {'a': 1}), {'b': 2})
