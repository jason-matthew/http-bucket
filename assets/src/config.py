"""
Retain application configuration
Manage environment variable consumption and defaults
"""
# core modules
import hashlib
import os
import re

# local modules
import util

# external config
# global                              env var                  default
MAX_CONTENT_LENGTH  = os.environ.get("MAX_CONTENT_LENGTH"   , "32mb").lower()
ARCHIVE_DIR         = os.environ.get("ARCHIVE_DIR"          , "/tmp/bucket")
CHECKSUM_TYPE       = os.environ.get("CHECKSUM_TYPE"        , "md5").lower()

# globals
logger = util.init_logger(__name__)
inputs = None

# alternative structure; currently not used
class CONSTANT:
    """
    Retain variables within a namespace
    Accessible using dot.notation
    """
    class DISK:
        class REQUIRED:
            SPACE = 2**30           # 1 gb
            INODE = 10**6           # 1 million
    class BUCKET:
        # hardlinking will be leveraged
        # directories should reside on same disk
        STAGING_DIR = os.path.join(ARCHIVE_DIR, "staging")
        EXPLODE_DIR = os.path.join(ARCHIVE_DIR, "archive")
        BLOB_DIR = os.path.join(ARCHIVE_DIR, "blob")
        DEFAULT_FILENAME = "blob"   # staging filename if not provided


def source_external_config():
    """
    Consume external config
    Raise exception for invalid values
    Returns:
        dict: flask app config additions
    """
    global inputs
    if inputs is not None:
        return inputs

    error_msg = (
        "Invalid input provided.  "
        "Failed to source application config"
    )
    inputs = {}
    max_content_regex = re.compile(r"^(\d+)(gb|mb|kb)?$")
    if max_content_regex.search(MAX_CONTENT_LENGTH):
        count, unit = max_content_regex.findall(MAX_CONTENT_LENGTH)[0]
        count = int(count)
        if unit == "gb":
            count = count * 2**30
        elif unit == "mb":
            count = count * 2**20
        elif unit == "kb":
            count = count * 2**10
        inputs["MAX_CONTENT_LENGTH"] = count
    else:
        raise EnvironmentError(
            "Invalid MAX_CONTENT_LENGTH format: '%s'."
            "<# bytes> or <#><unit> required (ie, 10mb).  %s"
            % (MAX_CONTENT_LENGTH, error_msg)
        )

    if os.path.isdir(ARCHIVE_DIR):
        pass
    elif os.path.exists(ARCHIVE_DIR):
        raise EnvironmentError(
            "Invalid ARCHIVE_DIR: '%s'.  "
            "Location exists but is not a directory.  %s"
            % (ARCHIVE_DIR, error_msg)
        )
    else:
        # attempt to create location
        try:
            logger.info(
                "Creating ARCHIVE_DIR: '%s'"
                % ARCHIVE_DIR
            )
            os.makedirs(ARCHIVE_DIR, exist_ok=True)
        except Exception as e:
            raise EnvironmentError(
                "Failed to create ARCHIVE_DIR: '%s'.  %s.  %s"
                % (ARCHIVE_DIR, e, error_msg)
            )
    inputs["UPLOAD_FOLDER"] = ARCHIVE_DIR

    # check disk
    avail_bytes, avail_inodes = util.check_disk(ARCHIVE_DIR)

    if avail_bytes < CONSTANT.DISK.REQUIRED.SPACE:
        available_gb = round(avail_bytes / 2**30, 2)
        required_gb = round(CONSTANT.DISK.REQUIRED.SPACE / 2**30, 2)
        raise EnvironmentError(
            "ARCHIVE_DIR does not have sufficient space.  "
            "%s GB required, but only %s GB available.  %s"
            % (required_gb, available_gb, error_msg)
        )
    if avail_inodes < CONSTANT.DISK.REQUIRED.INODE:
        raise EnvironmentError(
            "ARCHIVE_DIR does not have sufficient inodes.  "
            "%s required, but only %s available.  %s"
            % (CONSTANT.DISK.REQUIRED.INODE, avail_inodes, error_msg)
        )

    if CHECKSUM_TYPE not in hashlib.algorithms_available:
        raise EnvironmentError(
            "Invalid CHECKSUM_TYPE value: '%s'.  "
            "Supported algorithms: %s.  %s"
            % (CHECKSUM_TYPE, hashlib.algorithms_available, error_msg)
        )
    else:
        inputs["CHECKSUM_TYPE"] = CHECKSUM_TYPE

    logger.info(
        "Inputs accepted: %s"
        % inputs
    )
    return inputs