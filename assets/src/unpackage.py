"""
Utilities for decompressing archives

References:
https://docs.python.org/3/library/tarfile.html
https://docs.python.org/3/library/zipfile.html
"""

# core modules
import bz2
import gzip
import lzma
import os.path
import shutil
import tarfile
import zipfile

# installed modules
import magic

# local modules
import util

# globals
logger = util.init_logger(__name__)


class SafeExtract(object):
    """
    Retain functions is a namespace
    References:
    - https://stackoverflow.com/a/10077309
    """

    error_msg = (
        "Archive is attempting to extract outside of the dst directory.  "
        "Unwilling to continue"
    )

    @staticmethod
    def resolved(path):
        return os.path.realpath(os.path.abspath(path))

    @classmethod
    def badpath(cls, path, base):
        # os.path.join will ignore base if path is absolute
        return not cls.resolved(os.path.join(base,path)).startswith(base)

    @classmethod
    def badlink(cls, info, base):
        # Links are interpreted relative to the directory containing the link
        tip = cls.resolved(os.path.join(base, os.path.dirname(info.name)))
        return cls.badpath(info.linkname, base=tip)

    @classmethod
    def check_members_tar(cls, archive):
        base = cls.resolved(".")

        for finfo in archive.getmembers():
            if cls.badpath(finfo.name, base):
                raise RuntimeError(
                    "'%s' is blocked (illegal path).  %s"
                    % (finfo.name, cls.error_msg)
                )
            elif finfo.issym() and cls.badlink(finfo,base):
                raise RuntimeError(
                    "'%s' is blocked (symbolic link to '%s').  %s"
                    % (finfo.name, finfo.linkname, cls.error_msg)
                )
            elif finfo.islnk() and cls.badlink(finfo,base):
                raise RuntimeError(
                    "'%s' is blocked (hard link to '%s').  %s"
                    % (finfo.name, finfo.linkname, cls.error_msg)
                )

    @classmethod
    def check_members_zip(cls, archive):
        base = cls.resolved(".")

        # ZipFile.extractall() will not preserve symbolic links
        for finfo in archive.infolist():
            if cls.badpath(finfo.filename, base):
                raise RuntimeError(
                    "'%s' is blocked (illegal path).  %s"
                    % (finfo.filename, cls.error_msg)
                )


def tar(src, dst):
    """
    Explode archive to disk
    Args:
        src (str): file path
        dst (str): pre-existing destination directory
    Raises:
        RuntimeError: malicious tar provided
    """
    logger.info(
        "Extracting tar '%s' to '%s'"
        % (src, dst)
    )
    # tarfile module does not protect against malicously created archives
    # we need to consciously avoid extracting outside dst location

    # raise error if compressed archive provided
    archive = tarfile.open(src, 'r:')
    # raise error if extract attempts to alter anything outside of dst
    SafeExtract.check_members_tar(archive)
    archive.extractall(dst)
    archive.close()


def zip(src, dst):
    """
    Explode archive to disk
    Args:
        src (str): file path
        dst (str): pre-existing destination directory
    """
    logger.info(
        "Extracting zip '%s' to '%s'"
        % (src, dst)
    )

    archive = zipfile.ZipFile(src, 'r')
    # raise error if extract attempts to alter anything outside of dst
    SafeExtract.check_members_zip(archive)
    archive.extractall(dst)
    archive.close()


def gunzip(src, dst):
    """
    Decompress file to disk
    Args:
        src (str): file path
        dst (str): pre-existing destination directory
    """
    logger.info(
        "Decompressing gzip '%s' to '%s'"
        % (src, dst)
    )

    with gzip.open(src, 'rb') as f_in:
        with open(dst, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)


def bzip2(src, dst):
    """
    Decompress file to disk
    Args:
        src (str): file path
        dst (str): pre-existing destination directory
    """
    logger.info(
        "Decompressing bz2 '%s' to '%s'"
        % (src, dst)
    )

    with bz2.open(src, "rb") as f_in:
        with open(dst, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)


def xz(src, dst):
    """
    Decompress file to disk
    Args:
        file (str): file path
        dst (str): pre-existing destination directory
    """
    logger.info(
        "Decompressing xz '%s' to '%s'"
        % (src, dst)
    )

    with lzma.open(src, "rb") as f_in:
        with open(dst, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)