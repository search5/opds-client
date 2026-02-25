import time
import urllib.request
import urllib.error

from PyQt5.QtCore import QThread, pyqtSignal

load_translations()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FETCH_TIMEOUT = 60
_FETCH_RETRIES = 3
_FETCH_RETRY_DELAY = 5


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------

def _fetch(url: str, server: dict) -> bytes:
    auth = server.get('auth', 'none')
    if auth == 'basic':
        username = server.get('username', '')
        password = server.get('password', '')
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, url, username, password)
        auth_handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
        opener = urllib.request.build_opener(auth_handler)
    else:
        opener = urllib.request.build_opener()

    opener.addheaders = [
        ('User-Agent', 'CalibreOPDSClient/1.0'),
        ('Accept', 'application/atom+xml, application/xml, text/xml, */*'),
    ]

    last_error = None
    for attempt in range(_FETCH_RETRIES):
        try:
            with opener.open(url, timeout=_FETCH_TIMEOUT) as resp:
                content_type = resp.headers.get('Content-Type', '')
                data = resp.read()
            if 'text/html' in content_type:
                preview = data[:200].decode('utf-8', errors='replace').strip()
                raise ValueError(
                    _('Server returned HTML instead of XML (Content-Type: %s).\n'
                      'Please check the URL and authentication settings.\n\n'
                      'Response preview:\n%s') % (content_type, preview)
                )
            return data
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = e
            if attempt < _FETCH_RETRIES - 1:
                time.sleep(_FETCH_RETRY_DELAY)

    raise last_error


# ---------------------------------------------------------------------------
# Background fetch thread
# ---------------------------------------------------------------------------

class FetchThread(QThread):
    finished = pyqtSignal(bytes)
    error = pyqtSignal(str)

    def __init__(self, url, server, parent=None):
        super().__init__(parent)
        self.url = url
        self.server = server

    def run(self):
        try:
            self.finished.emit(_fetch(self.url, self.server))
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# Download thread
# ---------------------------------------------------------------------------

class DownloadThread(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, url, save_path, server, parent=None):
        super().__init__(parent)
        self.url = url
        self.save_path = save_path
        self.server = server

    def run(self):
        try:
            data = _fetch(self.url, self.server)
            with open(self.save_path, 'wb') as f:
                f.write(data)
            self.finished.emit(self.save_path)
        except Exception as e:
            self.error.emit(str(e))
