"""
Provide generic utilities
Module typically sourced by all peers
Importing local modules likely creates a circular dependency
"""

# core modules
import io
import logging
import os
import re
import unicodedata
import uuid

# avoid local module import


def init_logger(name, level=logging.INFO, stream=False):
    """
    Typically performed once per namesapce
    Re-init logger during subsequent calls
    Args:
        name (str): logger identifier
        level: DEBUG|INFO|WARNING|ERROR
    Returns:
        logger obj
    """
    logger = logging.getLogger(name)
    if logger is not None and len(logger.handlers):
        for handler in logger.handlers:
            if isinstance(handler, logging.NullHandler):
                logger.removeHandler(handler)

    if logger is not None and len(logger.handlers):
        logger.info("Logger '%s' already initialized" % name)
        logger.setLevel(level)
        return logger

    log_format = logging.Formatter('%(asctime)-15s %(levelname)-8s %(message)s')
    logger.setLevel(level)
    handler = logging.StreamHandler()
    handler.setFormatter(log_format)
    logger.addHandler(handler)
    return logger


def check_disk(path):
    """
    Determine available disk space and inodes
    Returns:
        tuple: disk space (bytes), inodes
    """
    # check disk space
    # https://man7.org/linux/man-pages/man3/statvfs.3.html
    # https://docs.python.org/3/library/os.html#os.statvfs

    # calculations made for ordinary users
    statvfs = os.statvfs(path)
    free_bytes = statvfs.f_frsize * statvfs.f_bavail
    free_inodes = statvfs.f_favail
    return free_bytes, free_inodes


def secure_filename(filename):
    """
    Retain local function to reduce module dependencies
    Args:
        filename (str): the filename to secure
    Returns:
        str: filename
    Reference:
        https://github.com/pallets/werkzeug/blob/0396223b29129cc7e284e3f69592e7da44021904/src/werkzeug/utils.py#L401
        https://github.com/pallets/werkzeug/blob/0396223b29129cc7e284e3f69592e7da44021904/LICENSE.rst
        Pass it a filename and it will return a secure version of it.  This
        filename can then safely be stored on a regular file system and passed
        to :func:`os.path.join`.  The filename returned is an ASCII only string
        for maximum portability.
        On windows systems the function also makes sure that the file is not
        named after one of the special device files.
        >>> secure_filename("My cool movie.mov")
        'My_cool_movie.mov'
        >>> secure_filename("../../../etc/passwd")
        'etc_passwd'
        >>> secure_filename('i contain cool \xfcml\xe4uts.txt')
        'i_contain_cool_umlauts.txt'
        The function might return an empty filename.  It's your responsibility
        to ensure that the filename is unique and that you abort or
        generate a random filename if the function returned an empty one.
    """

    _filename_ascii_strip_re = re.compile(r"[^A-Za-z0-9_.-]")
    _windows_device_files = (
        "CON",
        "AUX",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "LPT1",
        "LPT2",
        "LPT3",
        "PRN",
        "NUL",
    )
    filename = unicodedata.normalize("NFKD", filename)
    filename = filename.encode("ascii", "ignore").decode("ascii")

    for sep in os.path.sep, os.path.altsep:
        if sep:
            filename = filename.replace(sep, " ")

    filename = "_".join(filename.split())
    filename = str(_filename_ascii_strip_re.sub("",filename)).strip("._")

    # On nt a couple of special files are present in each folder.
    # We have to ensure that the target file is not such a filename.
    # In this case we prepend an underline
    if (
        os.name == "nt"
        and filename
        and filename.split(".")[0].upper() in _windows_device_files
    ):
        filename = f"_{filename}"

    return filename


class LogStream(object):
    """
    Short-lived logger object
    Write to STDOUT as well as StringIO
    Allow caller to retrieve logging statements
    """
    FORMAT = logging.Formatter('%(asctime)-25s %(name)-25s %(levelname)-8s %(message)s')

    def __init__(self, prefix, uid=None, level=logging.INFO):
        """
        Create logging and StringIO objects
        """
        # initialize all instance variables
        self.log = None
        self.stream = None
        self.msgs = None

        if uid is None:
            uid = uuid.uuid4().hex[:4]
        name = "%s.%s.%s" % (type(self).__name__, prefix, uid)
        logger = logging.getLogger(name)
        logger.setLevel(level)

        log_stream = io.StringIO()
        str_handler = logging.StreamHandler(log_stream)
        std_handler = logging.StreamHandler()

        logger.addHandler(str_handler)
        logger.addHandler(std_handler)

        for handler in logger.handlers:
            handler.setLevel(level)
            handler.setFormatter(self.FORMAT)

        self.log = logger
        self.stream = log_stream

    def __getattr__(self, item):
        """
        LogStream did not provide attribute or method
        Fall back to logger object
        """
        if self.log is None:
            raise RuntimeError(
                "Log has already been closed"
            )
        return getattr(self.log, item)

    def close(self):
        """
        Retrieve logged messsages
        Close out handlers
        Returns:
            list: logged messages
        """
        msgs = self.stream.getvalue()
        self.stream.flush()
        self.stream.close()

        while self.log.hasHandlers():
            handle = self.log.handlers[0]
            self.log.removeHandler(handle)
            handle.flush()
            handle.close()

        self.log = None
        self.stream = None
        self.msgs = msgs.splitlines()


