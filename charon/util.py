# -*- coding: utf-8 -*-

import sys
import time

def check_wait(test, initial=10, factor=1, max_tries=60):
    """Call function ‘test’ periodically until it returns True or a timeout occurs ."""
    wait = initial
    tries = 0
    while tries < max_tries and not test():
        time.sleep(wait)
        wait = wait * factor
        tries = tries + 1
        if tries == max_tries:
            raise Exception("operation timed out")
    return True
