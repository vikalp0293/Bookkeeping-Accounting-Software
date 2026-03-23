This folder is populated when you run the embedded Python build on Windows:

  npm run build:python-embed

That script downloads the Python embeddable package, installs pip and
requirements, and extracts everything here. The built app then ships
this folder so users do not need to install Python.

If you build the Windows installer on macOS/Linux without running
build:python-embed, this folder will be empty and users will need to
install Python 3.8+ themselves (or use the optional python-installer).

To bundle Python: run "npm run build:python-embed" on a Windows machine
before "npm run build:win".
