"""
Utilities for calculating file system attributes.

File checksums need to align with conventions used outside of this module
As an example, the following conventions are expected to yield the same result:
* /usr/bin/md5sum <file path>
* fclib.fs.calc.file_md5(<file_path>)
"""
# core modules
import hashlib
import os
import stat

# installed modules

# local modules
import util

# config modules

# globals
file_checksum_cache = {}    # { hashtype: { file-identifier: { last-modified: checksum } } }
logger = util.init_logger(__name__)


def file_checksum(path, hashtype="md5", block_size=4096):
    """
    Inspect file and calculate checksum value
    By default, cache will be used to mitigate redundancy.
    Cache is retained by combination of inode and last modified timestamp
    Use of optional argument can be used to force new calculation
    Args:
        path (str): file path
        hashtype (str): desired algorithm. argument conveyed to hashlib.new()
        block_size (int): (optional) calculation parameter
    Returns:
        (str): checksum value
    Raises:
        OSError: failed to read file
        TypeError: invalid argument type
        ValueError: invalid hash type
    """
    error_msg = "Unable to calculate file checksum"
    if not isinstance(path, str):
        raise TypeError(
            "Invalid file path provided: (%s, %s).  "
            "str required.  %s"
            % (type(path), path, error_msg)
        )
    if not isinstance(hashtype, str):
        raise TypeError(
            "Invalid hashtype provided: (%s, %s).  "
            "str required.  %s"
            % (type(hashtype), hashtype, error_msg)
        )
    if not isinstance(block_size, int):
        raise TypeError(
            "Invalid block_size provided: (%s, %s).  "
            "int required.  %s"
            % (type(block_size), block_size, error_msg)
        )

    # retain checksum cache
    # { hashtype: { file-identifier: { last-modified: checksum } } }
    # we need a mechanism to distinguish files
    # primary plan is to leverage device + inode
    # in the event device or inode is not identified, the file path is used
    file_stats = os.stat(path)
    device = file_stats.st_dev
    inode = file_stats.st_ino
    modified = file_stats.st_mtime
    if device == 0 or inode == 0:
        # os.stat is misbehaving or we're on a system which does not
        # provide this information (windows)
        file_identifier = os.path.realpath(path)
    else:
        file_identifier = "%s:%s" % (device, inode)

    # initialize cache
    cache = file_checksum_cache
    if hashtype not in cache:
        cache[hashtype] = {}
    if file_identifier not in cache[hashtype]:
        cache[hashtype][file_identifier] = {}
    if modified not in cache[hashtype][file_identifier]:
        # read file, calculate checksum, retain cache
        logger.debug(
            "Calculating hash for (file, identifier, modified): (%s, %s, %s)"
            % (path, file_identifier, modified)
        )
        cache[hashtype][file_identifier][modified] = \
            _file_checksum(path, hashtype, block_size)

    return cache[hashtype][file_identifier][modified]


def _file_checksum(path, hashtype, block_size):
    """
    Private function used to separate checksum calculation and cache maintenance
    Args:
        path (str): file path
        hashtype (str): desired algorithm. argument conveyed to hashlib.new()
        block_size (int): (optional) calculation parameter
    Returns:
        (str) checksum value
    Raises:
        OSError: failed to read file
        ValueError: invalid hash type
    """
    # private function, arguments previously validated
    with open(path, 'rb') as rf:
        h = hashlib.new(hashtype)
        for chunk in iter(lambda: rf.read(block_size), b''):
            h.update(chunk)
    return h.hexdigest()


def file_checksums_in_directory(path, *args, **kwargs):
    """
    Identify all files within a directory structure
    Determine checksum for all files
    Links and empty directories not captured within data structure
    Args:
        path (str): file path
        hashtype (str): desired algorithm. argument conveyed to hashlib.new()
        block_size (int): (optional) calculation parameter
    Returns:
        (dict): {relative_path: checksum, ...}
    Raises:
        OSError: failed to read file
        TypeError: invalid argument type
        ValueError: invalid hash type
    """

    # verify path ends with directory delimiter
    path = path.rstrip(os.sep) + os.sep

    # find all files; do not follow directory links
    files = []
    for dir_path, _, file_names in os.walk(path):
        for name in file_names:
            abs_path = os.path.join(dir_path, name)
            mode = os.stat(abs_path).st_mode
            if stat.S_ISREG(mode):
                # collect regular files (omit pipes and sockets)
                files.append(abs_path)
            else:
                # unknown file type
                logger.warning(
                    "Omitting '%s' from checksum calculation.  "
                    "Path is not a regular file"
                    % abs_path
                )


    # calculate checksums; retain relative path
    result = {}
    for filepath in files:
        rel_path = filepath.replace(path, "", 1)
        result[rel_path] = file_checksum(filepath, *args, **kwargs)

    return result
