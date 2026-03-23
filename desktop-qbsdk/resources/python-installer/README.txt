Python installer (32-bit) for fallback when embedded Python is not used.

INCLUDE (packaged in app):
  - python-3.11.9.exe   (32-bit only; required for QuickBooks COM)
  Download: https://www.python.org/ftp/python/3.11.9/python-3.11.9.exe

REMOVE (do not keep in this folder):
  - python-3.11.9-amd64.exe  (64-bit; incompatible with QuickBooks)
  - Any other .exe or files

Only python-3.11.9.exe is included in the installer build.
