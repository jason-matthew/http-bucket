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
import datetime
import hashlib
import io
import os
import re
import shutil
import traceback
import uuid

# installed modules
import magic

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
        Create directory path, including checksum/path
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


class Replicastore(Dirstore):
    """
    Leverage existing classes to facilitate Replica file paths
    """
    STORAGE_DIR = config.CONSTANT.BUCKET.REPLICA_DIR

    @classmethod
    def get_route(self, path):
        """
        Explicitly overwrite base class
        Replica manages directory paths, not checksums
        Args:
            path (list): subdirectories
        Returns:
            list of strings (subdir paths)
        Raises:
            TypeError: invalid argument
        """
        error_msg = "Failed to determine Replica route"
        if not isinstance(path, list):
            raise TypeError(
                "Invalid path provided: (%s, %s).  "
                "Directory path via list expected.  %s"
                % (type(path), path, error_msg)
            )
        return path


class _Action(object):
    """
    Base class for providing consumer operations
    """
    def __init__(self):
        uid = uuid.uuid4().hex[:4]
        cls_name = type(self).__name__

        self.uid = uid                              # (str) 4char unique identifier
        self.log = util.LogStream(cls_name, uid)    # (obj) LogStream emphemeral logging object


class _Stage(_Action):
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
        # establish logger
        super().__init__()

        spath = os.path.join(self.STAGING_DIR, self.uid)
        self.log.info(
            "Creating staging directory: '%s'"
            % spath
        )
        os.makedirs(spath, mode=0o777)

        # initialize all base instance variables
        self.staging_path = spath   # (str) staging directory path
        self.archive_path = None    # (str) (set when content archived) archive path
        self.file_path = None       # (str) (not used by all subclasses) staged file
        self.local_source = None    # (str) (not used by all subclasses) source file
        self.mime = None            # (str) (staged file) mime type
        self.checksum = None        # (str) (staged file) fingerprint
        self.error = None           # (str) exception msg
        self.exception = None       # (obj) Python Exception

    def get_absolute_path(self):
        """ Simple accessor; prioritize archived location """
        return self.archive_path or self.file_path

    def get_path(self):
        """ Simple accessor; prioritize uri """
        return self.get_uri() or self.get_relative_path()

    def get_relative_path(self):
        """
        Determine relative path to content from ARCHIVE_DIR
        """
        return self.get_absolute_path().replace(config.ARCHIVE_DIR, "", 1).lstrip("/\\")

    def get_uri(self):
        """
        Determine URL to content
        Requires ARCHIVE_URI to be provided when instance started
        """
        if config.ARCHIVE_URI is None:
            return None
        else:
            return os.path.join(config.ARCHIVE_URI, self.get_relative_path())


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
        finally:
            self.log.close()

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
        # Implementation not required by subclass
        pass

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
        # establish logger, staging location and file path
        super().__init__()

        # set upload destination; external process will save file
        fpath = os.path.join(self.staging_path, filename)
        self.file_path = fpath

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
        self.log.info(
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
            self.log.info(
                "File already stored in %s location(s)"
                % hardlinks
            )
        else:
            Blobstore.ensure_writeable(self.checksum)
            os.link(self.file_path, bpath)
            self.log.info(
                "Blob created: %s"
                % self.checksum
            )
        self.log.info(
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
        self.log.info(
            "Removing staging directory: '%s'"
            % self.staging_path
        )
        os.remove(self.file_path)       # single known file
        os.rmdir(self.staging_path)     # remove empty directory


class CompFile(File):
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
        # establish logger, staging location and file path
        super().__init__()

        # initialize all instance variables
        self.local_source = local_file       # (str) compressed file path (already exists on disk)

    def _unpackage(self):
        """
        Inspect mime type of src file
        Unpackage content to staging directory
        Raise:
            RuntimeError: mime type not supported
        """
        mime = magic.from_file(self.local_source, mime=True)
        if mime not in self.SUPPORTED_MIMETYPES:
            raise RuntimeError(
                "File is not a compressed file: '%s'.  "
                "Mime type identified '%s' is not supported: %s"
                % (self.local_source, mime, list(self.SUPPORTED_MIMETYPES.keys()))
            )
        call = self.SUPPORTED_MIMETYPES[mime]
        call(self.local_source, self.file_path)
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
        # establish logger, staging and destination directories
        super().__init__()

        # initialize all instance variables
        self.local_source = local_file       # (str) archive file path (already retained to disk)
        self.file_checksums = None          # (dict) file checksums { rel_path: checksum, ... }
        self.short_circuit = False          # (bool) skip unpackage, inspect, and store steps

    def _setup(self):
        """
        Spot-check if Dirstore already retains this archive
        Short-circuit if archive previously processed
        """
        # retain checksum which matches archive file
        # checksum will eventually be used when establishing archive locatiom
        self.checksum = calc.file_checksum(self.local_source, self.CHECKSUM_TYPE)
        self.mime = None

        self.archive_path = Dirstore.get_destination(self.checksum)
        if Dirstore.check_exists(self.checksum):
            self.log.info(
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

        mime = magic.from_file(self.local_source, mime=True)
        if mime not in self.SUPPORTED_MIMETYPES:
            raise RuntimeError(
                "File is not a archive package: '%s'.  "
                "Mime type identified '%s' is not supported: %s"
                % (self.local_source, mime, list(self.SUPPORTED_MIMETYPES.keys()))
            )
        call = self.SUPPORTED_MIMETYPES[mime]
        call(self.local_source, self.staging_path)
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
                self.log.debug(
                    "Creating directory: '%s'"
                    % dpath
                )
                os.makedirs(dpath, mode=0o777, exist_ok=True)
            for item in file_names:
                rel_path = os.path.join(rel_dir_path, item)
                if rel_path not in self.file_checksums:
                    self.log.warning(
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
                self.log.info(
                    "File '%s' already stored in %s location(s)"
                    % (rel_path, hardlinks)
                )
            else:
                Blobstore.ensure_writeable(checksum)
                os.link(abs_path, bpath)
                self.log.info(
                    "File '%s' retained in blobstore: %s"
                    % (rel_path, checksum)
                )
            self.log.info(
                "Blobstore retention confirmed: (%s -> %s)"
                % (abs_path, bpath)
            )

            os.link(bpath, apath)
            self.log.info(
                "Dirstore retention confirmed: (%s -> %s)"
                % (bpath, apath)
            )

    def _cleanup(self):
        """
        Remove staging directory from disk
        """
        self.log.info(
            "Removing staging directory: '%s'"
            % self.staging_path
        )
        shutil.rmtree(self.staging_path)     # remove entire directory structure


class Replicate(_Stage):
    """
    Duplicate content on disk using file and directory links
    """
    TIMESTAMP_FORMAT = "%Y%m%d.%H%M"
    ERROR_MSG = "Failed to process replicates"

    def __init__(self, source, name, headers):
        """
        Establish staging directory and retain knowledeg of pre-existing artifact
        Args:
            source (str): local file or directory
            name (str): replica name
            headers (dict): client request headers (keys already uppercased)
        Raises:
            FileExistsError: uuid directory collison; path already exists
        """
        # establish logger, staging and destination directories
        super().__init__()

        # normalize header keys via uppercase
        keys = list(headers.keys())
        for k in keys:
            headers[str(k).upper()] = headers[k]

        # initialize all instance variables
        self.local_source = source              # (str) archive path (either file or directory)
        self.name = util.secure_filename(name)  # (str) destination identifier (will be suffixed with date)
        self.request_headers = headers          # (dict) client-provided key/value pairs
        self.replica_matches = []               # (list) replicas to create
        self.replicas = []                      # (list) replicas created

    def get_paths(self):
        """ Simple accessor; prioritize uri """
        return self.get_uris() or self.get_relative_paths()

    def get_relative_paths(self):
        """
        Determine relative path to content from ARCHIVE_DIR
        """
        paths = []
        for replica in self.replicas:
            paths.append(replica.replace(config.ARCHIVE_DIR, "", 1).lstrip("/\\"))
        if len(paths):
            return paths
        else:
            return None

    def get_uris(self):
        """
        Determine URL to content
        Requires ARCHIVE_URI to be provided when instance started
        """
        if config.ARCHIVE_URI is None:
            return None
        else:
            paths = []
            for path in self.get_relative_paths() or []:
                paths.append(os.path.join(config.ARCHIVE_URI, path))
            if len(paths):
                return paths
            else:
                return None

    def _inspect(self):
        """
        Inspect request headers and server config
        Identify replicates which should be created
        """
        if config.REPLICATES is None:
            # log against module
            logger.warning(
                "Server is not configured to create replicates.  "
                "Replicate stage should not be called"
            )
            return

        for replicate_config in config.REPLICATES:
            replica_path = []
            partial_match = False
            for item in replicate_config:
                if config.ReplicatePath.is_dir(item):
                    replica_path.append(item)
                    continue

                # assumption: server config and client headers uppercased
                header = config.ReplicatePath.get_header(item)
                client_value = self.request_headers.get(header, "")
                if client_value == "":
                    replica_path.append(None)
                else:
                    secure_path = util.secure_filename(client_value)
                    if secure_path != client_value:
                        self.log.info(
                            "Replica destination does not resemble a linux directory name.  "
                            "Path has been modified: '%s' -> '%s'"
                            % (client_value, secure_path)
                        )
                    replica_path.append(secure_path)
                    partial_match = True
            if None in replica_path and partial_match:
                self.log.info(
                    "Replica criteria is not fully satisfied: %s -> %s.  "
                    "Operation can be completed by supplying full set of headers"
                    % (replicate_config, replica_path)
                )
            elif partial_match:
                self.log.info(
                    "Replica identified: %s -> %s"
                    % (replicate_config, replica_path)
                )
                self.replica_matches.append(replica_path)

        self.log.info(
            "%s replicas identified"
            % len(self.replica_matches)
        )

    def _determine_replica_name(self, dst_dir):
        """
        Inspect contents of directory
        Identify unique name which include datetime
        Args:
            dst_dir (str): pre-existing destination directory
        Returns:
            str: replica name (name.timestamp.index.extension)
        Raises:
            RuntimeError: invalid destination directory
            EnvironmentError: numerous replicas already exist
        """
        # ensure destination exists
        error_msg = "Unable to determine replica name"
        if not os.path.isdir(dst_dir):
            raise RuntimeError(
                "Destination directory does not exist: '%s'.  %s"
                % (dst_dir, error_msg)
            )

        name, extension = os.path.splitext(self.name)
        if os.path.isdir(self.local_source):
            # content has been extracted; drop extension
            extension = ""

        timestamp = datetime.datetime.utcnow().strftime(self.TIMESTAMP_FORMAT)
        limit = 100
        for i in range(0, limit):
            replica = "%s.%s.%s%s" % (name, timestamp, i, extension)
            if not os.path.exists(os.path.join(dst_dir, replica)):
                # new path identified
                return replica

        raise EnvironmentError(
            "Replica limit reached.  "
            "%s replicas already exist within '%s'.  %s"
            % (limit, dst_dir, error_msg)
        )

    def _determine_latest_link_name(self):
        """
        Determine "latest" link name
        Returns:
            str: link name (name.latest.extension)
        """
        if os.path.isfile(self.local_source):
            name, extension = os.path.splitext(self.name)
        else:
            name = self.name
            extension = ""

        return "%s.latest%s" % (name, extension)

    def _store(self):
        """
        Create replicas
        """
        if len(self.replica_matches) == 0:
            # request headers did not match server config
            # no operation to perform
            return

        for replica_path in self.replica_matches:
            dst_dir = Replicastore.get_destination(replica_path)
            # ensure directory exists
            self.log.info(
                "Creating replica '%s' within: %s"
                % (self.name, dst_dir)
            )
            Replicastore.ensure_writeable(replica_path)

            # determine replicate name
            replica_id = self._determine_replica_name(dst_dir)
            replica_dst = os.path.join(dst_dir, replica_id)

            if os.path.isfile(self.local_source):
                # blob replica
                # use hard link
                os.link(self.local_source, replica_dst)
                self.log.info(
                    "File replica established using hard link: '%s' -> '%s'"
                    % (replica_dst, self.local_source)
                )
            else:
                # archive/directory replica
                # use symbolic link
                rel_path = os.path.relpath(self.local_source, dst_dir)
                os.symlink(rel_path, replica_dst)
                self.log.info(
                    "Directory replica establish using symbolic link: '%s' -> '%s'"
                    % (replica_dst, rel_path)
                )

            # establish name.latest symbolic link
            latest_link_name = self._determine_latest_link_name()
            latest_link = os.path.join(dst_dir, latest_link_name)
            if os.path.exists(latest_link):
                os.unlink(latest_link)
            os.symlink(replica_id, latest_link)
            self.log.info(
                "Latest link established: '%s' -> '%s'"
                % (latest_link_name, replica_id)
            )

            # retain knowledge of replicas created
            self.replicas.append(replica_dst)

    def _cleanup(self):
        """
        Remove staging directory from disk
        Raises:
            OSError: staging directory populated with additional content
        """
        # cleanup expects no files to exist
        # step will fail if staging directory contains additional content
        self.log.info(
            "Removing staging directory: '%s'"
            % self.staging_path
        )
        os.rmdir(self.staging_path)     # remove empty directory


class Upload(_Action):
    """
    Facilitate file
    """
    DEFAULT_FILENAME = config.CONSTANT.BUCKET.DEFAULT_FILENAME

    def __init__(self, filename=DEFAULT_FILENAME, request_headers=None):
        """
        Create initial staging directory and File object
        """
        # establish logger
        super().__init__()

        # initialize all instance variables
        self.filename = filename            # (str) file uploaded
        self.headers = request_headers      # (dict) HTTP headers
        self.file_obj = File(filename)      # (File obj)
        self.compfile_obj = None            # (CompressedFile obj)
        self.archive_obj = None             # (Archive obj)
        self.replicate_obj = None           # (Replicate obj)
        self.result = None                  # (bool) pass/fail

    def get_upload_destination(self):
        """
        Specify location for external process to save upload
        """
        return self.file_obj.file_path

    def process(self):
        """
        Process uploaded file and retain within blobstore
        Leverage CompFile and Archive classes if file type is supported
        """
        obj = self.file_obj
        if obj.archive_path:
            raise RuntimeError(
                "Upload has already been processed.  "
                "Call made against completed object"
            )

        self.log.info(
            "Processing upload: '%s'"
            % (obj.get_absolute_path())
        )
        result = obj.process()

        if result and obj.mime in CompFile.SUPPORTED_MIMETYPES:
            self.log.info(
                "Compressed file of type '%s' recognized: '%s'"
                % (obj.mime, obj.get_absolute_path())
            )
            obj = self.compfile_obj = CompFile(obj.get_absolute_path())
            result = obj.process()

        if result and obj.mime in Archive.SUPPORTED_MIMETYPES:
            self.log.info(
                "Directory archive of type '%s' recognized: '%s'"
                % (obj.mime, obj.get_absolute_path())
            )
            obj = self.archive_obj = Archive(obj.get_absolute_path())
            result = obj.process()

        if result and self.headers and len(config.REPLICATES):
            self.log.info(
                "Checking if replication requested via HTTP headers"
            )
            obj = self.replicate_obj = Replicate(obj.get_absolute_path(), self.filename, self.headers)
            result = obj.process()

        if result is False:
            self.log.warning(
                "Upload processing unsuccessful.  See prior error"
            )
        self.result = result
        self.log.close()
        return result

    def get_api_response(self, log=True):
        """
        Collect results from obj instances
        Args:
            log (bool): include log statements within API response
        Returns:
            tuple: (dict, int)
            (response payload, status code)
        Raises:
            TypeError: invalid argument type
            ValueError: invalid argument value
        """
        if log not in [True, False]:
            # log against module, not this specific action
            logger.warning(
                "Invalid log value provided: (%s).  "
                "Reseting to default value"
                % type(log)
            )
            log = False

        if self.result is True:
            code = 200
        else:
            code = 500

        errors = []
        msgs = []
        for obj in [self.file_obj, self.compfile_obj, self.archive_obj, self.replicate_obj]:
            if obj is None:
                continue
            if obj.error:
                errors += obj.error
            msgs += obj.log.msgs
        msgs += self.log.msgs

        result = {
            "checksum": {
                "blob": self.file_obj.checksum,
                "decompressed": None if self.compfile_obj is None else self.compfile_obj.checksum,
                "archive": None if self.archive_obj is None else self.archive_obj.checksum,
            },
            "path": {
                "blob": self.file_obj.get_path(),
                "decompressed": None if self.compfile_obj is None else self.compfile_obj.get_path(),
                "archive": None if self.archive_obj is None else self.archive_obj.get_path(),
                "replicas": None if self.replicate_obj is None else self.replicate_obj.get_paths(),
            },
            "code": code,
            "status": errors if errors else "Success",
        }
        if log:
            # sort by timestamp characters (retain existing order for matching timestamps)
            result["log"] = sorted(msgs, key=lambda x:x[:24])

        return result, code
