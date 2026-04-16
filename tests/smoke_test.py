from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app


def extract_csrf_token(response) -> str:
    text = response.get_data(as_text=True)
    match = re.search(r'name="csrf_token" value="([^"]+)"', text)
    assert match, "csrf token not found"
    return match.group(1)


def main() -> None:
    app = create_app()
    client = app.test_client()

    login_page = client.get("/access/login")
    assert login_page.status_code == 200
    assert client.post(
        "/access/login",
        data={
            "csrf_token": extract_csrf_token(login_page),
            "access_secret": "viewer-123456",
            "next": "/",
        },
    ).status_code == 302
    assert client.get("/").status_code == 200
    assert client.get("/history").status_code == 200
    assert client.get("/library").status_code == 200
    assert client.get("/section/2026-04-12/own_track").status_code == 200
    assert client.get("/upload").status_code == 302

    admin_page = client.get("/admin/verify")
    client.post(
        "/admin/verify",
        data={
            "csrf_token": extract_csrf_token(admin_page),
            "access_secret": "admin-123456",
            "next": "/upload",
        },
    )
    assert client.get("/upload").status_code == 200
    assert client.get("/access/manage").status_code == 200

    print("smoke_test_ok")


if __name__ == "__main__":
    main()
