; Custom NSIS script for Sync Accounting QB SDK.
; Python is bundled with the app (embedded zip extracted to userData on first run).
; Do not add custom pages that check for Python or run pip install during setup.

!macro customInit
  ; No custom init (no Python check, no redirect to python.org)
!macroend

!macro customInstall
  ; No custom install (no pip install during setup; app installs deps on first launch)
!macroend
