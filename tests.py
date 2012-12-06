import nose
import sys

count = nose.loader.defaultTestLoader().loadTestsFromNames(['.']).countTestCases()
nose.main(argv=[ sys.argv[0], "--process-timeout=inf", "--processes=%d" % (count) ])
