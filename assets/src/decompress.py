"""
Utilities for decompressing archives

References:
https://docs.python.org/3/library/tarfile.html
https://docs.python.org/3/library/zipfile.html
"""

# core modules
import tarfile
import zipfile

# installed modules 
import magic

# local modules
import util

# globals
logger = util.init_logger(__name__)


def tar(file, dst):
    raise NotImplementedError

def zip(file, dst):
    raise NotImplementedError
