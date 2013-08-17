import unittest

from textwrap import dedent

from nixops.nix_expr import py2nix, RawValue


class PPrintTest(unittest.TestCase):
    def test_numeric(self):
        self.assertEqual(py2nix(123), "123")
        self.assertEqual(py2nix(-123), "builtins.sub 0 123")
        self.assertRaises(ValueError, py2nix, 123.4)

    def test_boolean(self):
        self.assertEqual(py2nix(True), "true")
        self.assertEqual(py2nix(False), "false")

    def test_null(self):
        self.assertEqual(py2nix(None), "null")

    def test_invalid(self):
        self.assertRaises(ValueError, py2nix, lambda: 123)
        self.assertRaises(ValueError, py2nix, Exception)

    def test_string(self):
        self.assertEqual(py2nix("xyz"), '"xyz"')
        self.assertEqual(py2nix("a'b\"c"), r'''"a'b\"c"''')
        self.assertEqual(py2nix("abc\ndef\nghi"), r'"abc\ndef\nghi"')
        self.assertEqual(py2nix("abc\ndef\nghi\n", maxwidth=0),
                         "''\n  abc\n  def\n  ghi\n''")
        self.assertEqual(py2nix("\\foo"), r'"\\foo"')
        self.assertEqual(py2nix("xx${yy}zz"), r'"xx\${yy}zz"')
        self.assertEqual(py2nix("xx\n${yy}\nzz\n", maxwidth=0),
                         "''\n  xx\n  ''${yy}\n  zz\n''")
        self.assertEqual(py2nix("xx\n''yy\nzz\n", maxwidth=0),
                         "''\n  xx\n  '''yy\n  zz\n''")

    def test_raw_value(self):
        self.assertEqual(py2nix({'a': RawValue('import <something>')}),
                         '{ a = import <something>; }')
        self.assertEqual(py2nix([RawValue("!")]),
                         '[ ! ]')

    def test_list(self):
        self.assertEqual(py2nix([1, 2, 3]), '[ 1 2 3 ]')
        self.assertEqual(py2nix(["a", "b", "c"]), '[ "a" "b" "c" ]')
        self.assertEqual(py2nix(["a\na\na\n", "b\nb\n", "c"]),
                         r'[ "a\na\na\n" "b\nb\n" "c" ]')
        self.assertEqual(py2nix(["a\na\na\n", "b\nb\n", "c"], maxwidth=15),
                         '[\n  "a\\na\\na\\n"\n  "b\\nb\\n"\n  "c"\n]')

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

        self.assertEqual(py2nix([
            [1, 2, 3],
            [4, 5, 6],
            [[6, 6, 6], [[7, 7, 7], [8, 8, 8], [9, 9, 9]]]
        ], maxwidth=12), match)

    def test_nested_singletons(self):
        match = dedent('''
        [ [ [
          1
          2
          [ [ 3 ] ]
        ] ] ]
        ''').strip()

        self.assertEqual(py2nix([[[1, 2, [[3]]]]], maxwidth=12), match)

    def test_attrkeys(self):
        self.assertEqual(py2nix({'aaa': 123}), '{ aaa = 123; }')
        self.assertEqual(py2nix({'a.a': 123}), '{ "a.a" = 123; }')
        self.assertEqual(py2nix({'\\': 123}), r'{ "\\" = 123; }')
        self.assertEqual(py2nix({'a1': 123}), '{ a1 = 123; }')
        self.assertEqual(py2nix({'1a': 123}), '{ "1a" = 123; }')
        self.assertEqual(py2nix({'_aa': 123}), '{ _aa = 123; }')
        self.assertRaises(KeyError, py2nix, {'': 123})
        self.assertRaises(KeyError, py2nix, {123: 123})

    def test_attrvalues(self):
        self.assertEqual(py2nix({'a': "abc"}), '{ a = "abc"; }')
        self.assertEqual(py2nix({'a': "a\nb\nc\n"}), r'{ a = "a\nb\nc\n"; }')
        self.assertEqual(py2nix({'a': [1, 2, 3]}), r'{ a = [ 1 2 3 ]; }')

    def test_nested_attrsets(self):
        match = dedent('''
        {
          aaa = {
            bbb.ccc = 123;
            ccc = 456;
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

        self.assertEqual(py2nix({
            'aaa': {
                'bbb': {
                    'ccc': 123,
                },
                'ccc': 456,
            },
            'xxx': [1, 2, 3],
            'yyy': {
                'y1': {'y2': {'y3': ["a", "b", {'c': 'd'}]}},
            },
        }, maxwidth=0), match)
