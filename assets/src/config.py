""" 
Retain application configuration
Manage environment variable consumption and defaults
"""

# external config
MAX_CONTENT_LENGTH = os.environ.get("MAX_CONTENT_LENGTH", "32mb").lower()
ARCHIVE_DIR = os.environ.get("ARCHIVE_DIR", "/tmp/bucket/archive")
TEMP_DIR = os.environ.get("ARCHIVE_TEMP_DIR", None)

# CONSTANTS
DISK_SPACE_REQUIRED = 2**30         # 1 gb
DISK_INODE_REQUIRED = 10**6         # 1 million





