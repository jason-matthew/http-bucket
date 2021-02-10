"""
Retain application configuration
Manage environment variable consumption and defaults
"""
# core modules
import hashlib
import json
import os
import re
import time

# installed modules
import requests

# local modules
import util

# external config
# global                              env var                  default
MAX_CONTENT_LENGTH  = os.environ.get("MAX_CONTENT_LENGTH"   , "32mb").lower()
CHECKSUM_TYPE       = os.environ.get("CHECKSUM_TYPE"        , "md5").lower()
ARCHIVE_DIR         = os.environ.get("ARCHIVE_DIR"          , "/tmp/bucket")
ARCHIVE_URI         = os.environ.get("ARCHIVE_URI"          , None)
# consume REPLICATE_0, REPLICATE_1, ... environment variables
# initialized later based on variables provided
REPLICATES          = []

# globals
logger = util.init_logger(__name__)
inputs = None


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
        BLOB_DIR    = os.path.join(ARCHIVE_DIR, "blob")
        EXPLODE_DIR = os.path.join(ARCHIVE_DIR, "explode")
        REPLICA_DIR = os.path.join(ARCHIVE_DIR, "replica")
        DEFAULT_FILENAME = "blob"   # staging filename if not provided


class ReplicatePath(object):
    """
    Instance instantiated during environment variable parsing
    """
    VARIABLE_REGEX = re.compile("^\${([a-z][a-z0-9-]*[a-z0-9])}$", re.IGNORECASE)
    ALPHANUM_REGEX = re.compile("^[a-z0-9]+$", re.IGNORECASE)

    @classmethod
    def is_dir(cls, value):
        """ Check if value looks like directory path """
        return bool(cls.ALPHANUM_REGEX.search(value))

    @classmethod
    def is_header(cls, value):
        """ Check if value looks like ${HEADER-TOKEN} """
        return bool(cls.VARIABLE_REGEX.search(value))

    @classmethod
    def get_header(cls, value):
        """ Extract variable name """
        if not cls.VARIABLE_REGEX.search(value):
            raise RuntimeError(
                "Token not provided.  Unable to retain replication path"
            )
        return cls.VARIABLE_REGEX.findall(value)[0].upper()


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
    else:
        raise EnvironmentError(
            "Invalid MAX_CONTENT_LENGTH format: '%s'."
            "<# bytes> or <#><unit> required (ie, 10mb).  %s"
            % (MAX_CONTENT_LENGTH, error_msg)
        )
    inputs["MAX_CONTENT_LENGTH"] = count

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
                "Failed to create ARCHIVE_DIR: '%s'.  %s: %s.  %s"
                % (ARCHIVE_DIR, type(e), e, error_msg)
            )
    inputs["ARCHIVE_DIR"] = ARCHIVE_DIR

    # argument not required
    if ARCHIVE_URI is not None:
        # raise error if URI is not accessible
        if os.path.isdir(ARCHIVE_URI):
            logger.info(
                "ARCHIVE_URI directory path provided.  Access confirmed: '%s'"
                % ARCHIVE_URI
            )
        else:
            try:
                sleep_time=2.4
                logger.info(
                    "Waiting for accompanying web server to start.  Sleeping: %s"
                    % sleep_time
                )
                time.sleep(sleep_time)
                response = requests.head(ARCHIVE_URI, verify=False, timeout=10)
                response.raise_for_status()
                logger.info(
                    "ARCHIVE_URI web path provider.  Access confirmed: '%s'"
                    % ARCHIVE_URI
                )
            except Exception as e:
                raise EnvironmentError(
                    "Failed to connect to ARCHIVE_URI: '%s'.  %s: %s.  %s"
                    % (ARCHIVE_URI, type(e), e, error_msg)
                )
    inputs["ARCHIVE_URI"] = ARCHIVE_URI

    if CHECKSUM_TYPE not in hashlib.algorithms_available:
        raise EnvironmentError(
            "Invalid CHECKSUM_TYPE value: '%s'.  "
            "Supported algorithms: %s.  %s"
            % (CHECKSUM_TYPE, hashlib.algorithms_available, error_msg)
        )
    inputs["CHECKSUM_TYPE"] = CHECKSUM_TYPE

    # archive replicates
    # providing additional doc to introduce the goals:
    # - enable clients to organize content outside of blob/dirstore
    # - enable multiple replicates
    # sequence:
    # - (1) admin specifies config via REPLICATE_# enviroment variables
    # - (2) server values take form 'dir/${HEADER-NAME}/...'
    # - (3) during file upload, clients provide additional information using request headers
    # - (4) client values take form '<HEADER-NAME>: <HEADER-VALUE>'...
    # - (5) bucket application will create '<HEADER-VALUE>/...' directory structure
    # - (6) directory contents will be a symlink to archive storage
    for index in range(0,10):
        external_var = "REPLICATE_%s" % index
        external_val = os.environ.get(external_var, "")
        if external_val == "":
            continue
        replicate_error = (
            "Invalid replicate config (%s: '%s').  "
            "Value should convey directory path comprised of "
            "alphanumeric directory names and '${Header-Name}' tokens"
            % (external_var, external_val)
        )
        replicate_path = []
        header_named = False
        for path in external_val.strip(" /.").split("/"):
            if ReplicatePath.is_dir(path):
                replicate_path.append(path.upper())
            elif ReplicatePath.is_header(path):
                replicate_path.append(path.upper())
                header_named = True
            else:
                raise EnvironmentError(
                    "%s.  '%s' does not resemble a valid replica path.  %s"
                    % (replicate_error, path, error_msg)
                )
        if header_named is False:
            raise EnvironmentError(
                "%s.  A ${Header-Name} token was not included within replica path.  %s"
                % (replicate_error, error_msg)
            )
        logger.info(
            "Replicate path accepted: %s"
            % replicate_path
        )
        REPLICATES.append(replicate_path)
    inputs["REPLICATES"] = REPLICATES

    logger.info(
        "Inputs accepted: %s"
        % inputs
    )
    return inputs


def verify_disk():
    """
    Spot-check disk resources
    """
    error_msg = (
        "Capacity issues will likely be encountered.  "
        "Unwilling to continue"
    )

    # ensure disk has space and indoes availability
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
