"""
Provide generic utilities 
Module typically sourced by all peers 
Importing local modules likely creates a circular dependency
"""

# core modules 
import logging
import os

# avoid local module import


def init_logger(name, level=logging.INFO):
    """
    Typically performed once per namesapce
    Re-init logger during subsequent calls
    """
    logger = logging.getLogger(name)
    if logger is not None and len(logger.handlers):
        # ensure logger is not initialized with 1 or more NullHandler objects
        # remove additional NullHandler objects with recursive call
        handler = logger.handlers[0]
        if isinstance(handler, logging.NullHandler):
            logger.removeHandler(handler)
            return init_logger(name, level)

        logger.debug("Logger '%s' already initialized" % name)
        logger.setLevel(level)
        return logger

    log_format = '%(asctime)-15s %(levelname)-8s %(message)s'
    logger.setLevel(level)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(log_format))
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

