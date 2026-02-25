import os
import time
import tempfile
import urllib.request
import urllib.error
import urllib.parse
from urllib.parse import urljoin

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QLabel, QStackedWidget, QListWidget, QListWidgetItem,
    QTableView, QAbstractItemView, QLineEdit, QMessageBox,
    QHeaderView,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from calibre.gui2 import error_dialog, info_dialog

try:
    _USER_ROLE = Qt.UserRole
except AttributeError:
    _USER_ROLE = Qt.ItemDataRole.UserRole

from .config import load_servers, save_servers, get_last_server, set_last_server
from .opds_parser import parse_feed, NavigationFeed, AcquisitionFeed
from .model import BookTableModel
from .server_dialog import ServerDialog

load_translations()


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------

_FETCH_TIMEOUT = 60
_FETCH_RETRIES = 3
_FETCH_RETRY_DELAY = 5


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
# Server manager dialog
# ---------------------------------------------------------------------------

class ServerManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_('Manage Servers'))
        self.setMinimumWidth(420)
        self.setMinimumHeight(300)
        self.servers = load_servers()
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        layout = QHBoxLayout(self)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        btn_layout = QVBoxLayout()
        self.btn_add    = QPushButton(_('Add'))
        self.btn_edit   = QPushButton(_('Edit'))
        self.btn_delete = QPushButton(_('Delete'))
        self.btn_up     = QPushButton(_('Move Up'))
        self.btn_down   = QPushButton(_('Move Down'))
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addSpacing(10)
        btn_layout.addWidget(self.btn_up)
        btn_layout.addWidget(self.btn_down)
        btn_layout.addStretch()
        btn_close = QPushButton(_('Close'))
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

        self.btn_add.clicked.connect(self._add)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_up.clicked.connect(self._move_up)
        self.btn_down.clicked.connect(self._move_down)
        btn_close.clicked.connect(self.accept)

    def _refresh_list(self):
        self.list_widget.clear()
        for s in self.servers:
            self.list_widget.addItem(s['name'])

    def _add(self):
        dlg = ServerDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self.servers.append(dlg.get_server())
            save_servers(self.servers)
            self._refresh_list()

    def _edit(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        dlg = ServerDialog(self, self.servers[row])
        if dlg.exec_() == QDialog.Accepted:
            self.servers[row] = dlg.get_server()
            save_servers(self.servers)
            self._refresh_list()
            self.list_widget.setCurrentRow(row)

    def _delete(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        name = self.servers[row]['name']
        if QMessageBox.question(
            self, _('Confirm Delete'),
            _('Are you sure you want to delete server "%s"?') % name,
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            self.servers.pop(row)
            save_servers(self.servers)
            self._refresh_list()

    def _move_up(self):
        row = self.list_widget.currentRow()
        if row <= 0:
            return
        self.servers[row - 1], self.servers[row] = self.servers[row], self.servers[row - 1]
        save_servers(self.servers)
        self._refresh_list()
        self.list_widget.setCurrentRow(row - 1)

    def _move_down(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.servers) - 1:
            return
        self.servers[row + 1], self.servers[row] = self.servers[row], self.servers[row + 1]
        save_servers(self.servers)
        self._refresh_list()
        self.list_widget.setCurrentRow(row + 1)


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class OPDSDialog(QDialog):
    def __init__(self, gui, icon, do_add_books):
        super().__init__(gui)
        self.gui = gui
        self.do_add_books = do_add_books
        self.setWindowTitle(_('OPDS Client'))
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)

        self._servers = load_servers()
        self._url_stack = []
        self._breadcrumb = []
        self._current_feed = None
        self._fetch_thread = None
        self._download_thread = None

        self._build_ui()
        self._populate_server_combo()

        last = get_last_server()
        if self._servers:
            idx = min(last, len(self._servers) - 1)
            self.server_combo.setCurrentIndex(idx)
            self._load_root()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        # Top: server selector
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel(_('Server:')))
        self.server_combo = QComboBox()
        self.server_combo.setMinimumWidth(200)
        top_layout.addWidget(self.server_combo, 1)
        self.btn_manage = QPushButton(_('Manage Servers'))
        top_layout.addWidget(self.btn_manage)
        main_layout.addLayout(top_layout)

        # Navigation bar
        nav_layout = QHBoxLayout()
        self.btn_back = QPushButton(_('◄ Back'))
        self.btn_back.setEnabled(False)
        nav_layout.addWidget(self.btn_back)
        self.btn_refresh = QPushButton(_('↻ Refresh'))
        nav_layout.addWidget(self.btn_refresh)
        self.lbl_breadcrumb = QLabel(_('Path: Home'))
        nav_layout.addWidget(self.lbl_breadcrumb, 1)
        main_layout.addLayout(nav_layout)

        # Content area (stack)
        self.stack = QStackedWidget()

        self.nav_list = QListWidget()
        self.stack.addWidget(self.nav_list)

        self.book_table = QTableView()
        self.book_model = BookTableModel()
        self.book_table.setModel(self.book_model)
        try:
            self.book_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.book_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            _stretch = QHeaderView.Stretch
            _rtc = QHeaderView.ResizeToContents
        except AttributeError:
            self.book_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.book_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            _stretch = QHeaderView.ResizeMode.Stretch
            _rtc = QHeaderView.ResizeMode.ResizeToContents
        self.book_table.horizontalHeader().setSectionResizeMode(0, _stretch)
        self.book_table.horizontalHeader().setSectionResizeMode(1, _rtc)
        self.book_table.horizontalHeader().setSectionResizeMode(2, _rtc)
        self.book_table.horizontalHeader().setSectionResizeMode(3, _rtc)
        self.stack.addWidget(self.book_table)

        main_layout.addWidget(self.stack, 1)

        # Bottom: search + download
        bottom_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(_('Enter search terms...'))
        self.btn_search = QPushButton(_('Search'))
        bottom_layout.addWidget(QLabel(_('Search:')))
        bottom_layout.addWidget(self.search_edit, 1)
        bottom_layout.addWidget(self.btn_search)
        bottom_layout.addSpacing(20)
        self.btn_download = QPushButton(_('Download Selected'))
        self.btn_download.setEnabled(False)
        bottom_layout.addWidget(self.btn_download)
        main_layout.addLayout(bottom_layout)

        # Pagination
        page_layout = QHBoxLayout()
        self.btn_prev = QPushButton('\u25c4')
        self.btn_prev.setFixedWidth(30)
        self.btn_prev.setEnabled(False)
        self.lbl_page = QLabel('')
        self.btn_next = QPushButton('\u25ba')
        self.btn_next.setFixedWidth(30)
        self.btn_next.setEnabled(False)
        page_layout.addStretch()
        page_layout.addWidget(QLabel(_('Page:')))
        page_layout.addWidget(self.btn_prev)
        page_layout.addWidget(self.lbl_page)
        page_layout.addWidget(self.btn_next)
        page_layout.addStretch()
        main_layout.addLayout(page_layout)

        # Signals
        self.btn_manage.clicked.connect(self._on_manage_servers)
        self.server_combo.currentIndexChanged.connect(self._on_server_changed)
        self.btn_back.clicked.connect(self._on_back)
        self.btn_refresh.clicked.connect(self._on_refresh)
        self.nav_list.itemDoubleClicked.connect(self._on_nav_item_clicked)
        self.btn_search.clicked.connect(self._on_search)
        self.search_edit.returnPressed.connect(self._on_search)
        self.btn_download.clicked.connect(self._on_download)
        self.btn_next.clicked.connect(self._on_next_page)
        self.book_table.selectionModel().selectionChanged.connect(self._on_book_selection)

        self._next_url = None
        self._prev_urls = []
        self._current_url = None

    # ------------------------------------------------------------------
    # Server combo
    # ------------------------------------------------------------------

    def _populate_server_combo(self):
        self.server_combo.blockSignals(True)
        self.server_combo.clear()
        for s in self._servers:
            self.server_combo.addItem(s['name'])
        self.server_combo.blockSignals(False)

    def _current_server(self):
        idx = self.server_combo.currentIndex()
        if 0 <= idx < len(self._servers):
            return self._servers[idx]
        return None

    def _on_server_changed(self, idx):
        set_last_server(idx)
        self._url_stack.clear()
        self._breadcrumb.clear()
        self._prev_urls.clear()
        self._load_root()

    def _on_manage_servers(self):
        prev_server = self._current_server()
        dlg = ServerManagerDialog(self)
        dlg.exec_()
        self._servers = load_servers()
        current_name = self.server_combo.currentText()
        self._populate_server_combo()

        idx = 0
        for i, s in enumerate(self._servers):
            if s['name'] == current_name:
                idx = i
                break
        self.server_combo.blockSignals(True)
        self.server_combo.setCurrentIndex(idx)
        self.server_combo.blockSignals(False)

        new_server = self._current_server()
        if new_server and (
            prev_server is None
            or prev_server.get('url') != new_server.get('url')
            or prev_server.get('auth') != new_server.get('auth')
            or prev_server.get('username') != new_server.get('username')
            or prev_server.get('password') != new_server.get('password')
        ):
            self._load_root()

    def _on_refresh(self):
        if self._current_url:
            self._fetch_url(self._current_url)
        else:
            self._load_root()

    # ------------------------------------------------------------------
    # Feed loading
    # ------------------------------------------------------------------

    def _load_root(self):
        server = self._current_server()
        if not server:
            return
        self._url_stack.clear()
        self._breadcrumb = [_('Home')]
        self._update_breadcrumb()
        self._fetch_url(server['url'])

    def _fetch_url(self, url: str):
        server = self._current_server()
        if not server:
            return

        if self._current_url and not url.startswith('http'):
            url = urljoin(self._current_url, url)

        self._current_url = url
        self.setEnabled(False)

        if self._fetch_thread and self._fetch_thread.isRunning():
            self._fetch_thread.quit()
            self._fetch_thread.wait()

        self._fetch_thread = FetchThread(url, server, self)
        self._fetch_thread.finished.connect(self._on_fetch_done)
        self._fetch_thread.error.connect(self._on_fetch_error)
        self._fetch_thread.start()

    def _on_fetch_done(self, data: bytes):
        self.setEnabled(True)
        try:
            feed = parse_feed(data)
        except Exception as e:
            error_dialog(self, _('Parse Error'), str(e), show=True)
            return

        self._current_feed = feed
        self._update_breadcrumb()

        if isinstance(feed, NavigationFeed):
            self._show_navigation(feed)
        else:
            self._show_acquisition(feed)

    def _on_fetch_error(self, msg: str):
        self.setEnabled(True)
        error_dialog(self, _('Connection Error'), msg, show=True)

    # ------------------------------------------------------------------
    # Navigation view
    # ------------------------------------------------------------------

    def _show_navigation(self, feed: NavigationFeed):
        self.stack.setCurrentIndex(0)
        self.nav_list.clear()
        self.btn_download.setEnabled(False)
        self._update_pagination(None)

        for entry in feed.entries:
            item = QListWidgetItem('\U0001f4c1  ' + entry.title)
            item.setData(_USER_ROLE, entry)
            self.nav_list.addItem(item)

    def _on_nav_item_clicked(self, item):
        entry = item.data(_USER_ROLE)
        if not entry or not entry.url:
            return
        self._url_stack.append(self._current_url)
        self._breadcrumb.append(entry.title)
        self._update_breadcrumb()
        self._fetch_url(entry.url)

    # ------------------------------------------------------------------
    # Acquisition view
    # ------------------------------------------------------------------

    def _show_acquisition(self, feed: AcquisitionFeed):
        self.stack.setCurrentIndex(1)
        self.book_model.set_entries(feed.entries)
        self.book_table.resizeColumnsToContents()
        self._update_pagination(feed.next_url)

    def _on_book_selection(self):
        selected = self.book_table.selectionModel().selectedRows()
        self.btn_download.setEnabled(len(selected) > 0)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _on_search(self):
        query = self.search_edit.text().strip()
        if not query:
            return
        server = self._current_server()
        if not server:
            return

        base_url = server['url']
        search_url = base_url + ('&' if '?' in base_url else '?') + 'q=' + urllib.parse.quote(query)

        self._url_stack.append(self._current_url)
        self._breadcrumb.append(_('Search: %s') % query)
        self._update_breadcrumb()
        self._fetch_url(search_url)

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    def _update_pagination(self, next_url):
        self._next_url = next_url
        self.btn_next.setEnabled(bool(next_url))
        self.btn_prev.setEnabled(bool(self._prev_urls))
        if next_url or self._prev_urls:
            self.lbl_page.setText('%d' % (len(self._prev_urls) + 1))
        else:
            self.lbl_page.setText('')

    def _on_next_page(self):
        if not self._next_url:
            return
        self._prev_urls.append(self._current_url)
        self._fetch_url(self._next_url)

    # ------------------------------------------------------------------
    # Back navigation
    # ------------------------------------------------------------------

    def _on_back(self):
        if not self._url_stack:
            return
        prev_url = self._url_stack.pop()
        if self._breadcrumb:
            self._breadcrumb.pop()
        self._update_breadcrumb()
        self._prev_urls.clear()
        self._fetch_url(prev_url)

    def _update_breadcrumb(self):
        self.lbl_breadcrumb.setText(_('Path: ') + ' > '.join(self._breadcrumb))
        self.btn_back.setEnabled(len(self._url_stack) > 0)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _on_download(self):
        selected_rows = self.book_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        entries = [self.book_model.entry(idx.row()) for idx in selected_rows]
        server = self._current_server()

        for entry in entries:
            if not entry.formats:
                QMessageBox.information(
                    self, _('Download'),
                    _('No downloadable formats available for "%s".') % entry.title
                )
                continue
            self._download_entry(entry, server)

    def _pick_format(self, entry):
        if len(entry.formats) == 1:
            return entry.formats[0]

        from PyQt5.QtWidgets import QInputDialog
        labels = [
            '%s  (%s)' % (f['type'].upper(), self._fmt_size_str(f.get('size', 0)))
            for f in entry.formats
        ]
        item, ok = QInputDialog.getItem(
            self, _('Select Format'),
            _('Select a format to download for "%s":') % entry.title,
            labels, 0, False
        )
        if not ok:
            return None
        return entry.formats[labels.index(item)]

    @staticmethod
    def _fmt_size_str(size):
        if size <= 0:
            return _('Unknown size')
        if size >= 1024 * 1024:
            return '%.1fMB' % (size / (1024 * 1024))
        if size >= 1024:
            return '%.1fKB' % (size / 1024)
        return '%dB' % size

    def _download_entry(self, entry, server):
        fmt = self._pick_format(entry)
        if fmt is None:
            return

        url = fmt['url']
        if not url.startswith('http'):
            url = urljoin(self._current_url, url)

        ext = fmt['type'].lower()
        prefix = entry.title.replace('/', '_')[:60] + '_'
        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.' + ext, prefix=prefix)
        os.close(tmp_fd)

        self.setEnabled(False)
        self._download_thread = DownloadThread(url, tmp_path, server, self)
        self._download_thread.finished.connect(
            lambda p: self._on_download_done(p, entry))
        self._download_thread.error.connect(self._on_download_error)
        self._download_thread.start()

    def _on_download_done(self, path: str, entry):
        self.setEnabled(True)
        if self.do_add_books:
            self.do_add_books([path], entry)
        else:
            info_dialog(self, _('Download Complete'),
                        _('"%s" downloaded to:\n%s') % (entry.title, path), show=True)

    def _on_download_error(self, msg: str):
        self.setEnabled(True)
        error_dialog(self, _('Download Error'), msg, show=True)


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


# ---------------------------------------------------------------------------
# InterfaceAction
# ---------------------------------------------------------------------------

from calibre.gui2.actions import InterfaceAction


class OPDSClientAction(InterfaceAction):
    name = 'OPDS Client'
    action_spec = (_('OPDS Client'), None,
                   _('Browse and download books from OPDS servers.'), None)
    popup_type = 0
    allowed_in_toolbar = True
    allowed_in_menu = True

    def genesis(self):
        icon = get_icons('image/opds_client_icon.png')
        self.qaction.setIcon(icon)
        self.qaction.triggered.connect(self.show_dialog)

    def show_dialog(self):
        d = OPDSDialog(self.gui, self.qaction.icon(), self._add_books)
        d.exec_()

    def _add_books(self, paths, entry=None):
        from calibre.ebooks.metadata.book.base import Metadata
        db = self.gui.current_db
        add_action = self.gui.iactions['Add Books']

        if entry is not None:
            mi = Metadata(entry.title, entry.authors or [_('Unknown')])
            if entry.publisher:
                mi.publisher = entry.publisher
            db.import_book(mi, paths)
            add_action.refresh_gui(len(paths), set_current_row=0)
            for p in paths:
                try:
                    os.remove(p)
                except OSError:
                    pass
        else:
            from functools import partial
            from calibre.gui2.add import Adder
            Adder(
                paths,
                db=db,
                parent=self.gui,
                callback=partial(self._on_added, add_action=add_action, tmp_paths=list(paths)),
                pool=self.gui.spare_pool(),
            )

    def _on_added(self, adder, add_action, tmp_paths):
        add_action._files_added(adder)
        for p in tmp_paths:
            try:
                os.remove(p)
            except OSError:
                pass
