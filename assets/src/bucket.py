"""
Provide utilities for storing file system content

Additional reading:
https://github.com/torvalds/linux/commit/800179c9b8a1e796e441674776d11cd4c05d61d7
https://unix.stackexchange.com/a/260191
https://unix.stackexchange.com/a/377719
http://man7.org/linux/man-pages/man5/proc.5.html (search, protected_hardlinks)

Design references:
https://quickshiftin.com/blog/2014/06/organize-directory-structure-large-dataset
"""

# core modules
import hashlib
import os
import re
import uuid

# installed modules
import magic
from werkzeug.utils import secure_filename

# local modules
import calc
import config
import decompress
import util

# constants

# globals
logger = util.init_logger(__name__)


class Blobstore(object):
    """
    Dictate structure and location to retain artifacts
    External operations are expected to establish blobs via hardlinks
    """
    WORKING_DIR = config.CONSTANT.BUCKET.BLOB_DIR
    CHECKSUM_TYPE = config.CHECKSUM_TYPE
    CHECKSUM_REGEX = re.compile(r"^[0-9a-f]{8,}", re.IGNORECASE)       # min 8 characters required

    @classmethod
    def get_route(cls, checksum):
        """
        Identify pieces of checksum
        Generate list of subdir paths which lead to the storage destination
        Final item in list should only exist if unit is stored
        Args:
            checksum (str): checksum value
        Refs:
            Interesting discussion surrounding hashing and directory layout
            https://quickshiftin.com/blog/2014/06/organize-directory-structure-large-dataset/
        Returns:
            list of strings (subdir paths)
        Raises:
            TypeError: invalid argument
            ValueError: checksum does not conform to expectations
        """
        # type/value checking
        error_msg = "Failed to determine checksum route"
        checks = [
            isinstance(checksum, str),
            cls.CHECKSUM_REGEX.search(checksum),
        ]
        if not all(checks):
            raise TypeError(
                "Invalid checksum provided: (%s, %s).  "
                "Checksum does not match '%s'.  %s"
                % (type(checksum), checksum, cls.CHECKSUM_REGEX.pattern, error_msg)
            )

        # normalize value and establish subdir structure
        checksum = checksum.lower()
        return [
            # Deconstruct into: 2char, 2char, full checksum
            checksum[:2],
            checksum[2:4],
            checksum
        ]

    @classmethod
    def get_destination(cls, checksum):
        """
        Given a checksum, identify the final destination
        Create intermediary directories
        Returns:
            str: absolute path to storage location
        Raises:
            TypeError: invalid argument
            ValueError: checksum does not conform to expectations
        """
        route = cls.get_route(checksum)
        return os.path.join(cls.WORKING_DIR, *route)

    @classmethod
    def ensure_writeable(cls, checksum):
        """
        Create directories leading to specific checksum
        """
        fpath = cls.get_destination(checksum)
        dpath = os.path.dirname(fpath)
        os.makedirs(dpath, mode=0o777, exist_ok=True)

    @classmethod
    def check_exists(cls, checksum):
        """
        Check if checksum already retained on disk
        Returns:
            bool: blob already stored
        """
        dst = cls.get_destination(checksum)
        return os.path.exists(dst)


class Dirstore(object):
    """
    Dictate structure and location to retain artifacts
    """
    pass


class _Stage(object):
    """
    Base class for temp file operations 
    """
    STAGING_DIR = config.CONSTANT.BUCKET.STAGING_DIR

    def __init__(self):
        """ 
        Create new staging directory
        Raises:
            FileExistsError: uuid directory collison; path already exists
        """
        uid = uuid.uuid4().hex[:8]
        dpath = os.path.join(self.STAGING_DIR, uid)
        logger.info(
            "Creating staging directory: '%s'" 
            % dpath
        )
        os.makedirs(dpath, mode=0o777)
        
        # initialize all base instance variables
        self.uid = uid          # (str) 8char unique identifier
        self.dpath = dpath      # (str) directory path
        self.error = None       # (str) exception msg
        self.exception = None   # (obj) Python Exception

    def process(self):
        """ 
        Called once after file is saved to disk
        Inspect uploaded content
        Establish hardlinks within blobstore
        If all successful, cleanup directory
        """
        error_msg = (
            "Failed to process content: '%s'" 
            % self.dpath
        )
        try:
            self._inspect()
            self._store()
            self._cleanup()
        except (OSError, TypeError, Exception) as e:
            msg = (
                "%s: %s.  %s"
                % (type(e).__name__, e, error_msg)
            )
            logger.error(msg)
            self.error = msg
            self.exception = e

    def _inspect(self):
        """
        Interogate file system content
        """
        raise NotImplementedError("Subclass did not implement this method")

    def _store(self):
        """
        Retain content outside of staging directory
        """
        raise NotImplementedError("Subclass did not implement this method")
    
    def _cleanup(self):
        """
        Remove staging directory from disk
        """
        raise NotImplementedError("Subclass did not implement this method")
    

class Blob(_Stage):
    """
    Transfer uploaded file content to disk 

    General sequence:
    - (local) Establish uuid location and file path
    - (external) Write file
    - (local) Determine file checksum and mimetype
    - (local) Retain content in blobstore
    - (local) Cleanup staging directory
    """
    DEFAULT_FILENAME = config.CONSTANT.BUCKET.DEFAULT_FILENAME
    CHECKSUM_TYPE = config.CHECKSUM_TYPE
    
    def __init__(self, filename=DEFAULT_FILENAME):
        """ 
        Determine initial location to retain upload
        Subsequent operations will process file
        Args:
            filename (str): uploaded filename (not provided for PUT requests)
        Raises:
            FileExistsError: uuid directory collison; path already exists
        """
        # establish destination location
        super().__init__()
        fpath = os.path.join(self.dpath, secure_filename(filename))

        # initialize all instance variables
        self.fpath = fpath      # (str) file path
        self.bpath = None       # (str) blob path
        self.mime = None        # (str) mime type 
        self.checksum = None    # (str) file fingerprint

    def get_file_path(self):
        """ Simple accessor """
        return self.bpath or self.fpath
        
    def _inspect(self):
        """
        Calculate checksum
        Determine mime type
        Raises:
            EnvironmentError: path does not exist
            TypeError: path not string
            TypeError: block size not int
            ValueError: invalid argument value
            ValueError: unsupported hash type
        """
        # validation that external processor has provided file implicitly occurs
        self.checksum = calc.file_checksum(self.fpath, self.CHECKSUM_TYPE)
        self.mime = magic.from_file(self.fpath, mime=True)
        logger.info(
            "File inspected '%s': (%s, %s)"
            % (self.fpath, self.mime, self.checksum)
        )

    def _store(self):
        """ 
        Ensure blobstore retains staged content
        """
        self.bpath = Blobstore.get_destination(self.checksum)
        if Blobstore.check_exists(self.checksum):
            hardlinks = os.stat(self.bpath).st_nlink
            logger.info(
                "File already stored in %s location(s)" 
                % hardlinks
            )
        else:
            Blobstore.ensure_writeable(self.checksum)
            os.link(self.fpath, self.bpath)
            logger.info(
                "Blob created: %s" 
                % self.checksum 
            )
        logger.info(
            "File retention confirmed: (%s, %s)"
            % (self.fpath, self.bpath)
        )

    def _cleanup(self):
        """
        Remove staging directory from disk
        Raises:
            OSError: staging directory populated with additional content
        """
        # cleanup expects single file to exist
        # step will fail if staging directory contains custom content 
        logger.info(
            "Removing staging directory: '%s'" 
            % self.dpath
        )
        os.remove(self.fpath)       # single known file
        os.rmdir(self.dpath)        # remove empty directory


class Archive(_Stage):
    """
    Unpackage directory archives (ie. tgz, zip)
    """
    EXPLODE_DIR = config.CONSTANT.BUCKET.EXPLODE_DIR
    SUPPORTED_MIMETYPES = {
        # python-magic mimetype :   call   
        "application/x-tar"     :   decompress.tar,
        "application/x-xz"      :   decompress.tar,
        "application/x-gzip"    :   decompress.tar,
        "application/x-bzip2"   :   decompress.tar,
        "application/zip"       :   decompress.zip,
    }

    def __init__(self, fpath):
        """ 
        Create new explode directory
        Args:
            fpath (str): absolute file path
        Raises:
            FileExistsError: uuid directory collison; path already exists
        """
        # establish staging and destination directories
        super().__init__()
        apath = os.path.join(self.EXPLODE_DIR, self.uid)

        # initialize all instance variables
        self.apath = apath      # archive path
    

