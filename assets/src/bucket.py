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
import shutil
import traceback
import uuid

# installed modules
import magic
from werkzeug.utils import secure_filename

# local modules
import calc
import config
import unpackage
import util

# constants
CHECKSUM_TYPE = config.CHECKSUM_TYPE

# globals
logger = util.init_logger(__name__)


class _Store(object):
    """
    Base class for retaining blobs and decompressed archives
    """
    CHECKSUM_REGEX = re.compile(r"^[0-9a-f]{8,}", re.IGNORECASE)       # min 8 characters required

    @property
    def STORAGE_DIR(self):
        """ Provided by subclass """
        raise NotImplementedError(
            "Class variable not implemented"
        )

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
        return os.path.join(cls.STORAGE_DIR, *route)


class Blobstore(_Store):
    """
    Dictate structure and location to retain artifacts
    External operations are expected to establish blobs via hardlinks
    """
    STORAGE_DIR = config.CONSTANT.BUCKET.BLOB_DIR

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


class Dirstore(_Store):
    """
    Dictate structure and location to retain artifacts
    """
    STORAGE_DIR = config.CONSTANT.BUCKET.EXPLODE_DIR

    @classmethod
    def ensure_writeable(cls, checksum):
        """
        Create directory path, including checksum
        """
        dpath = cls.get_destination(checksum)
        os.makedirs(dpath, mode=0o777, exist_ok=True)

    @classmethod
    def check_exists(cls, checksum):
        """
        Check if folder already exists and contains content
        Returns:
            bool: blob already stored
        """
        dst = cls.get_destination(checksum)
        if os.path.exists(dst) and len(os.listdir(dst)):
            return True
        else:
            return False


class _Stage(object):
    """
    Base class for temp file operations
    """
    STAGING_DIR = config.CONSTANT.BUCKET.STAGING_DIR
    CHECKSUM_TYPE = config.CHECKSUM_TYPE

    @property
    def ERROR_MSG(self):
        """ Provided by subclass """
        raise NotImplementedError(
            "Class variable not implemented"
        )

    def __init__(self):
        """
        Create new staging directory
        Raises:
            FileExistsError: uuid directory collison; path already exists
        """
        uid = uuid.uuid4().hex[:8]
        spath = os.path.join(self.STAGING_DIR, uid)
        logger.info(
            "Creating staging directory: '%s'"
            % spath
        )
        os.makedirs(spath, mode=0o777)

        # initialize all base instance variables
        self.uid = uid              # (str) 8char unique identifier
        self.staging_path = spath   # (str) staging directory path
        self.archive_path = None    # (str) (set when content archived) archive path
        self.file_path = None       # (str) (not used by all subclasses) staged file
        self.source_file = None     # (str) (not used by all subclasses) source file
        self.mime = None            # (str) (staged file) mime type
        self.checksum = None        # (str) (staged file) fingerprint
        self.error = None           # (str) exception msg
        self.exception = None       # (obj) Python Exception
        self.warnings = []          # (list) warning statements generated during bucket processing
        self.infos = []             # (list) info statments generated during bucket processing
        self.debugs = []            # (list) debug statements generated during bucket processing

    def get_path(self):
        """ Simple accessor; prioritize archived location """
        return self.archive_path or self.file_path

    def get_relative_path(self):
        """
        Determine relative path to content from ARCHIVE_DIR
        """
        return self.get_path().replace(config.ARCHIVE_DIR, "", 1)

    def debug(self, msg):
        """
        Capture debug messages and emit logging statements
        """
        self.debugs.append(msg)
        logger.debug(msg)

    def info(self, msg):
        """
        Capture info messages and emit logging statements
        """
        self.infos.append(msg)
        logger.info(msg)

    def warning(self, msg):
        """
        Capture warning messages and emit logging statements
        """
        self.warnings.append(msg)
        logger.warning(msg)

    def process(self, msg=""):
        """
        Called once after file is available
        Inspect uploaded content
        Establish hardlinks within blobstore
        If all successful, cleanup directory
        Args:
            msg (str): additional error str
        Returns:
            bool: pass/fail
        """
        error_msg = (
            "%s.  Staging directory retained: '%s'"
            % (self.ERROR_MSG, self.staging_path)
        )
        try:
            self._sequence()
            return True
        except (OSError, TypeError, Exception) as e:
            cls_type = type(self).__name__
            err_type = type(e).__name__
            msg = (
                "%s processing failed.  %s: %s.  %s"
                % (cls_type, err_type, e, error_msg)
            )
            logger.exception(msg)
            self.error = msg
            self.exception = e
            return False

    def _sequence(self):
        """
        Facilitate multiple actions
        Allow child classes to overwrite
        """
        self._setup()
        self._unpackage()
        self._inspect()
        self._store()
        self._cleanup()

    def _setup(self):
        """
        Generic method to allow custom actions
        """
        pass

    def _unpackage(self):
        """
        Unpackage compressed file or explode archive
        """
        raise NotImplementedError("Subclass did not implement this method")

    def _inspect(self):
        """
        Inspect file system content
        Determine checksum(s) and mime type
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


class File(_Stage):
    """
    Provide staging directory to save file
    Transfer uploaded file content to blobstore

    General sequence:
    - (__init__) Establish staging location and file path
    - (external) Write file to staging directory
    - (_inspect) Determine file checksum and mimetype
    - (_store) Retain content in blobstore
    - (_cleanup) Cleanup staging directory
    """
    DEFAULT_FILENAME = config.CONSTANT.BUCKET.DEFAULT_FILENAME
    ERROR_MSG = "Failed to process blob"

    def __init__(self, filename=DEFAULT_FILENAME):
        """
        Determine initial location to retain upload
        Subsequent operations will process file
        Args:
            filename (str): uploaded filename (not provided for PUT requests)
        Raises:
            FileExistsError: uuid directory collison; path already exists
        """
        # establish staging location and file path
        super().__init__()
        fpath = os.path.join(self.staging_path, secure_filename(filename))

        # set upload destination; external process will save file
        self.file_path = fpath

    def _unpackage(self):
        """ Operation not needed for File type"""
        pass

    def _inspect(self):
        """
        Calculate checksum and determine mime type
        Store results to instance variables
        Raises:
            OSError: path does not exist
            TypeError: path not string
            TypeError: block size not int
            ValueError: invalid argument value
            ValueError: unsupported hash type
        """
        # validation that external processor has provided file implicitly occurs
        self.checksum = calc.file_checksum(self.file_path, self.CHECKSUM_TYPE)
        self.mime = magic.from_file(self.file_path, mime=True)
        self.info(
            "File inspected '%s': (%s, %s)"
            % (self.file_path, self.mime, self.checksum)
        )

    def _store(self):
        """
        Ensure blobstore retains staged content
        """
        bpath = Blobstore.get_destination(self.checksum)
        if Blobstore.check_exists(self.checksum):
            hardlinks = os.stat(bpath).st_nlink
            self.info(
                "File already stored in %s location(s)"
                % hardlinks
            )
        else:
            Blobstore.ensure_writeable(self.checksum)
            os.link(self.file_path, bpath)
            self.info(
                "Blob created: %s"
                % self.checksum
            )
        self.info(
            "File retention confirmed: (%s -> %s)"
            % (self.file_path, bpath)
        )
        self.archive_path = bpath

    def _cleanup(self):
        """
        Remove staging directory from disk
        Raises:
            OSError: staging directory populated with additional content
        """
        # cleanup expects single file to exist
        # step will fail if staging directory contains additional content
        self.info(
            "Removing staging directory: '%s'"
            % self.staging_path
        )
        os.remove(self.file_path)       # single known file
        os.rmdir(self.staging_path)     # remove empty directory


class CompressedFile(File):
    """
    Create staging directory and uncompress pre-existing file

    General sequence
    - (external) Compressed file written to disk
    - (__init__) Establish staging location
    - (_unpackage) Determine compressed minetype, decompress to staging direcotry
    - (_inspect) Determine file checksum and mime type
    - (_store) Retain content in blobstore
    - (_cleanup) Cleanup staging directory
    """
    ERROR_MSG = "Failed to process compressed file"
    SUPPORTED_MIMETYPES = {
        # python-magic mimetype :   call
        "application/gzip"      :   unpackage.gunzip,
        "application/x-gzip"    :   unpackage.gunzip,
        "application/x-xz"      :   unpackage.xz,
        "application/x-bzip2"   :   unpackage.bzip2,
    }

    def __init__(self, local_file):
        """
        Establish staging directory and retain knowledeg of local, pre-existing file
        Args:
            local_file (str): local compressed file (likely a blob path)
        Raises:
            FileExistsError: uuid directory collison; path already exists
        """
        # establish staging location and file path
        super().__init__()

        # initialize all instance variables
        self.source_file = local_file       # (str) compressed file path (already exists on disk)

    def _unpackage(self):
        """
        Inspect mime type of src file
        Unpackage content to staging directory
        Raise:
            RuntimeError: mime type not supported
        """
        mime = magic.from_file(self.source_file, mime=True)
        if mime not in self.SUPPORTED_MIMETYPES:
            raise RuntimeError(
                "File is not a compressed file: '%s'.  "
                "Mime type identified '%s' is not supported: %s"
                % (self.source_file, mime, list(self.SUPPORTED_MIMETYPES.keys()))
            )
        call = self.SUPPORTED_MIMETYPES[mime]
        call(self.source_file, self.file_path)
        # TODO: assess file ownership and timestamp


class Archive(_Stage):
    """
    Unpackage directory archives (ie. tar, zip)

    General sequence:
    - (external) Decompressed archive written to disk
    - (__init__) Establish staging location
    - (_inspect) Determine compressed archive checksum and mimetype
    - (_inspect) Explode to staging directory, determine file checksums
    - (_store) Retain content in blobstore
    - (_store) Determine archive directory stucture, hardlink files to blobs
    - (_cleanup) Cleanup staging directory
    """
    ERROR_MSG = "Failed to process directory archive"
    SUPPORTED_MIMETYPES = {
        # python-magic mimetype :   call
        "application/x-tar"     :   unpackage.tar,
        "application/zip"       :   unpackage.zip,
    }

    def __init__(self, local_file):
        """
        Establish staging directory and retain knowledeg of local, pre-existing archive
        Args:
            local_file (str): local archive (likely a blob path)
        Raises:
            FileExistsError: uuid directory collison; path already exists
        """
        # establish staging and destination directories
        super().__init__()

        # initialize all instance variables
        self.source_file = local_file       # (str) archive file path (already retained to disk)
        self.file_checksums = None          # (dict) file checksums { rel_path: checksum, ... }
        self.short_circuit = False          # (bool) skip unpackage, inspect, and store steps

    def _setup(self):
        """
        Spot-check if Dirstore already retains this archive
        Short-circuit if archive previously processed
        """
        # retain checksum which matches archive file
        # checksum will eventually be used when establishing archive locatiom
        self.checksum = calc.file_checksum(self.source_file, self.CHECKSUM_TYPE)
        self.mime = None

        self.archive_path = Dirstore.get_destination(self.checksum)
        if Dirstore.check_exists(self.checksum):
            self.info(
                "Archive already stored: %s"
                % self.archive_path
            )
            self.short_circuit = True


    def _unpackage(self):
        """
        Inspect mime type of src file
        Unpackage content to staging directory
        Raise:
            RuntimeError: mime type not supported
        """
        if self.short_circuit:
            # Content already retained.  No need to unpackage again
            return

        mime = magic.from_file(self.source_file, mime=True)
        if mime not in self.SUPPORTED_MIMETYPES:
            raise RuntimeError(
                "File is not a archive package: '%s'.  "
                "Mime type identified '%s' is not supported: %s"
                % (self.source_file, mime, list(self.SUPPORTED_MIMETYPES.keys()))
            )
        call = self.SUPPORTED_MIMETYPES[mime]
        call(self.source_file, self.staging_path)
        # TODO: assess directory structure ownership and timestamps

    def _inspect(self):
        """
        Inspect unpackaged file structure
        """
        if self.short_circuit:
            # Content already retained.  No need to calculate checksums
            return

        # generate data structure describing archive contents
        # - retain { rel_path: checksum, ... }
        # - symbolic links are not included
        self.file_checksums = calc.file_checksums_in_directory(self.staging_path, self.CHECKSUM_TYPE)

    def _store(self):
        """
        Ensure every file within the staging directory is retained in blobstore
        Ensure directory structure is retained within dirstore
        """
        if self.short_circuit:
            # Content already retained
            return

        # establish empty directory structure using Dirstore
        # log warnings for any staging files which will not transfer
        apath = self.archive_path
        Dirstore.ensure_writeable(self.checksum)
        for dir_path, dir_names, file_names in os.walk(self.staging_path):
            rel_dir_path = dir_path.replace(self.staging_path, "", 1)
            for item in dir_names:
                rel_path = os.path.join(rel_dir_path, item)
                dpath = os.path.join(apath, rel_dir_path, item)
                self.debug(
                    "Creating directory: '%s'"
                    % dpath
                )
                os.makedirs(dpath, mode=0o777, exist_ok=True)
            for item in file_names:
                rel_path = os.path.join(rel_dir_path, item)
                if rel_path not in self.file_checksums:
                    self.warning(
                        "Omitting file '%s' from archive.  Checksum does not "
                        "exist which implies path is not a regular file"
                        % rel_path
                    )

        # store files using Blobstore
        # replicate file within Dirstore
        for rel_path, checksum in self.file_checksums.items():
            abs_path = os.path.join(self.staging_path, rel_path)
            apath = os.path.join(self.archive_path, rel_path)
            bpath = Blobstore.get_destination(checksum)
            if Blobstore.check_exists(checksum):
                hardlinks = os.stat(bpath).st_nlink
                self.info(
                    "File '%s' already stored in %s location(s)"
                    % (rel_path, hardlinks)
                )
            else:
                Blobstore.ensure_writeable(checksum)
                os.link(abs_path, bpath)
                self.info(
                    "File '%s' retained in blobstore: %s"
                    % (rel_path, checksum)
                )
            self.info(
                "Blobstore retention confirmed: (%s -> %s)"
                % (abs_path, bpath)
            )

            os.link(bpath, apath)
            self.info(
                "Dirstore retention confirmed: (%s -> %s)"
                % (bpath, apath)
            )

    def _cleanup(self):
        """
        Remove staging directory from disk
        """
        self.info(
            "Removing staging directory: '%s'"
            % self.staging_path
        )
        shutil.rmtree(self.staging_path)     # remove entire directory structure


class _Action(object):
    """
    Base class for providing consumer operations
    """
    pass


class Upload(_Action):
    """
    Facilitate file
    """
    DEFAULT_FILENAME = config.CONSTANT.BUCKET.DEFAULT_FILENAME

    def __init__(self, filename=DEFAULT_FILENAME):
        """
        Create initial staging directory and File object
        """
        # initialize all instance variables
        self.file_obj = File(filename)      # (File obj)
        self.compressed_obj = None          # (CompressedFile obj)
        self.archive_obj = None             # (Archive obj)
        self.result = None                  # bool: pass/fail

    def get_upload_destination(self):
        """
        Specify location for external process to save upload
        """
        return self.file_obj.file_path

    def process(self):
        """
        Process uploaded file and retain within blobstore
        Leverage CompressedFile and Archive classes if file type is supported
        """
        obj = self.file_obj
        if obj.archive_path:
            raise RuntimeError(
                "Upload has already been processed.  "
                "Call made against completed object"
            )

        logger.info(
            "Processing upload: '%s'"
            % (obj.get_path())
        )
        result = obj.process()

        if result and obj.mime in CompressedFile.SUPPORTED_MIMETYPES:
            logger.info(
                "Compressed file of type '%s' recognized: '%s'"
                % (obj.mime, obj.get_path())
            )
            obj = self.compressed_obj = CompressedFile(obj.get_path())
            result = obj.process()

        if result and obj.mime in Archive.SUPPORTED_MIMETYPES:
            logger.info(
                "Directory archive of type '%s' recognized: '%s'"
                % (obj.mime, obj.get_path())
            )
            obj = self.archive_obj = Archive(obj.get_path())
            result = obj.process()

        if result is False:
            logger.warning(
                "Upload processing unsuccessful.  See prior error"
            )
        self.result = result
        return result

    def get_api_response(self, log=True, log_level="info"):
        """
        Collect results from obj instances
        Args:
            log (bool): include log statements within API response
            log_level (str): include subset of logging statements
        Returns:
            tuple: (dict, int)
            (response payload, status code)
        Raises:
            TypeError: invalid argument type
            ValueError: invalid argument value
        """
        if log not in [True, False]:
            logger.warning(
                "Invalid log value provided: (%s).  "
                "Reseting to default value"
                % type(log)
            )
            log = False
        if log_level not in ["debug", "info", "warning", "error"]:
            logger.warning(
                "Invalid log_level value provided: (%s, %s).  "
                "Reseting to default value"
                % (type(log_level), log_level)
            )
            log_level = "warning"

        if self.result is True:
            code = 200
        else:
            code = 500

        debugs = []
        infos = []
        warnings = []
        errors = []
        for obj in [self.file_obj, self.compressed_obj, self.archive_obj]:
            if obj is None:
                continue
            if obj.error:
                errors.append(obj.error)
            warnings += obj.warnings
            infos += obj.infos
            debugs += obj.debugs
        if len(errors) == 0:
            errors = None
        if len(warnings) == 0:
            warnings = None
        if len(infos) == 0:
            infos = None
        if len(debugs) == 0:
            debugs = None

        result = {
            "checksum": {
                "blob": self.file_obj.checksum,
                "decompressed": None if self.compressed_obj is None else self.compressed_obj.checksum,
                "archive": None if self.archive_obj is None else self.archive_obj.checksum,
            },
            "path": {
                "blob": self.file_obj.get_relative_path(),
                "decompressed": None if self.compressed_obj is None else self.compressed_obj.get_relative_path(),
                "archive": None if self.archive_obj is None else self.archive_obj.get_relative_path(),
            },
            "log": {
                "debug": debugs,
                "info": infos,
                "warning": warnings,
                "error": errors,
            },
            "code": code,
            "status": errors if errors else "Success",
        }
        if log_level in ["info", "warning", "error"]:
            del result["log"]["debug"]
        if log_level in ["warning", "error"]:
            del result["log"]["info"]
        if log_level in ["error"]:
            del result["log"]["warning"]
        if log is False:
            del result["log"]

        return result, code
