"""
Constants for BTK.

These constants are used by various modules for sensible defaults.
Many are now also available via the config system.
"""

# Network timeouts (in seconds)
DEFAULT_REQUEST_TIMEOUT = 10
REACHABILITY_CHECK_TIMEOUT = 5
FAVICON_DOWNLOAD_TIMEOUT = 5

# Limits
MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 1000
MAX_URL_LENGTH = 2048
MAX_TAG_LENGTH = 100
MAX_TAGS_PER_BOOKMARK = 50

# Batch processing
DEFAULT_BATCH_SIZE = 100
DEFAULT_MAX_WORKERS = 5

# Display limits
DEFAULT_LIST_LIMIT = 50
DEFAULT_SEARCH_RESULTS_LIMIT = 100
