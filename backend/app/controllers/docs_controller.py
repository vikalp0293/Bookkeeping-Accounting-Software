"""
Documentation Controller
Serves user documentation and guides.
User guide is served from backend/app/static/user-guide/index.html (Sync Accounting QB SDK).
"""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, HTMLResponse, Response, RedirectResponse
from pathlib import Path

router = APIRouter(prefix="/docs", tags=["Documentation"])

# backend/app/static/user-guide/index.html (app/controllers -> app -> static)
_USER_GUIDE_HTML = Path(__file__).resolve().parent.parent / "static" / "user-guide" / "index.html"


def _get_user_guide_html() -> str:
    """Read static/user-guide/index.html and return as-is (direct HTML/CSS)."""
    if not _USER_GUIDE_HTML.exists():
        raise FileNotFoundError(f"User guide not found: {_USER_GUIDE_HTML}")
    with open(_USER_GUIDE_HTML, "r", encoding="utf-8") as f:
        return f.read()


@router.get("/user-guide")
async def get_user_guide():
    """Serve the Sync Accounting QB SDK user guide (from static/user-guide/index.html)."""
    try:
        html_content = _get_user_guide_html()
        return HTMLResponse(content=html_content)
    except FileNotFoundError as e:
        return PlainTextResponse(str(e), status_code=404)
    except Exception as e:
        return PlainTextResponse(
            f"Error reading user guide: {str(e)}",
            status_code=500
        )


@router.get("/user-guide/download")
async def download_user_guide():
    """Download the user guide as an HTML file."""
    try:
        html_content = _get_user_guide_html()
        return Response(
            content=html_content,
            media_type="text/html",
            headers={
                "Content-Disposition": "attachment; filename=Sync-Accounting-QB-SDK-User-Guide.html"
            }
        )
    except FileNotFoundError as e:
        return PlainTextResponse(str(e), status_code=404)
    except Exception as e:
        return PlainTextResponse(
            f"Error reading user guide: {str(e)}",
            status_code=500
        )


# backend/installers folder (backend = app/controllers -> app -> backend)
_INSTALLERS_DIR = Path(__file__).resolve().parent.parent.parent / "installers"

# Slug -> filename for QB SDK user guide downloads (files in backend/installers)
_INSTALLER_FILES = {
    "app": "Sync Accounting QB SDK Setup 1.0.0.exe",
    "qbsdk": "QBSDK170.exe",
    "python": "python-3.11.9.exe",
}


@router.get("/download/installer")
async def download_installer_redirect():
    """Redirect to QB SDK app installer (backward compatibility)."""
    return RedirectResponse(url="/docs/download/installer/app", status_code=302)


@router.get("/download/installer/{slug}")
async def download_installer_by_slug(slug: str):
    """
    Download an installer from backend/installers.
    slug: app | qbsdk | python
    - app    -> Sync Accounting QB SDK Setup 1.0.0.exe
    - qbsdk  -> QBSDK170.exe (QuickBooks SDK)
    - python -> python-3.11.9.exe
    """
    from fastapi.responses import FileResponse

    if slug not in _INSTALLER_FILES:
        return PlainTextResponse(
            f"Unknown installer: {slug}. Use one of: app, qbsdk, python.",
            status_code=404,
            media_type="text/plain",
        )
    filename = _INSTALLER_FILES[slug]
    installer_path = _INSTALLERS_DIR / filename
    if not installer_path.exists():
        return PlainTextResponse(
            f"Installer not found: {filename}. Place it in backend/installers/.",
            status_code=404,
            media_type="text/plain",
        )
    try:
        return FileResponse(
            path=str(installer_path),
            filename=filename,
            media_type="application/x-msdownload",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        return PlainTextResponse(
            f"Error serving installer: {str(e)}",
            status_code=500,
        )

