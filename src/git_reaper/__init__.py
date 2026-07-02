"""git-reaper: reap structured knowledge from repositories."""

try:
    from git_reaper._version import __version__
except ImportError:  # no VCS metadata and no build hook output; should not happen in installs
    __version__ = "0.0.0"

__all__ = ["__version__"]
