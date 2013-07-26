import nose
import sys
import os

if __name__ == "__main__":
    nose.main(argv=[sys.argv[0], "--with-xunit", "--with-coverage",
                    "--cover-inclusive", "--cover-xml",
                    "--cover-xml-file=coverage.xml", "--cover-html",
                    "--cover-html-dir=./html", "--cover-package=nixops",
                    "-e", "^tests\.py$"] + sys.argv[1:])
