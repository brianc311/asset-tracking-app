# Asset Tracking (desktop)

A **separate** desktop copy of Asset Tracking. It has its own database, login, and HTTPS port. It does **not** share data with `c:\#App\asset-tracking`.

Double-click **`run_desktop.bat`**. A window opens for the laptop. The phone can scan on the same Wi-Fi.

## First run

1. Install [Python 3.12+](https://www.python.org/downloads/) if needed (check **Add python.exe to PATH**).
2. Double-click `run_desktop.bat`.
3. Wait while it creates `.venv`, installs packages, and migrates.
4. Sign in with **admin** / **admin123**, then change that password.
5. On the phone (same Wi-Fi), open the URL shown in the window title, for example `https://192.168.30.73:8445/scan/`.
6. First phone visit: **Advanced → Proceed** (local certificate). Camera needs HTTPS.

Keep the black console window and the app window open while you scan.

## How this differs from the website copy

| | Website folder (`asset-tracking`) | This desktop app |
|---|---|---|
| Folder | `c:\#App\asset-tracking` | `c:\#App\asset-tracking-app` |
| Start | `.\run_dev_https.bat` | `run_desktop.bat` |
| HTTPS port | 8444 | **8445** |
| Database | its own `db.sqlite3` | its own `db.sqlite3` |

You can run both at once. Assets added in one do not appear in the other.

## reCAPTCHA

This copy starts with Google **test** keys so login works on `localhost` and `192.168.x.x`. The checkbox may say it is for testing only. That is expected.

## Stop

Close the Asset Tracking window. That also stops the phone URL.
