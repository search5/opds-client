from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QRadioButton,
    QButtonGroup, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QMessageBox, QListWidget,
)
from PyQt5.QtCore import Qt

from .config import load_servers, save_servers

load_translations()


class ServerDialog(QDialog):
    """Server add/edit dialog."""

    def __init__(self, parent=None, server=None):
        super().__init__(parent)
        self.setWindowTitle(_('Edit Server') if server else _('Add Server'))
        self.setMinimumWidth(380)
        self._build_ui()
        if server:
            self._load(server)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText('http://example.com/opds')
        form.addRow(_('Server Name:'), self.name_edit)
        form.addRow(_('URL:'), self.url_edit)

        # Auth method
        auth_widget = QWidget()
        auth_layout = QHBoxLayout(auth_widget)
        auth_layout.setContentsMargins(0, 0, 0, 0)
        self.rb_none = QRadioButton(_('None'))
        self.rb_basic = QRadioButton('Basic Auth')
        self.rb_none.setChecked(True)
        self._auth_group = QButtonGroup(self)
        self._auth_group.addButton(self.rb_none, 0)
        self._auth_group.addButton(self.rb_basic, 1)
        auth_layout.addWidget(self.rb_none)
        auth_layout.addWidget(self.rb_basic)
        auth_layout.addStretch()
        form.addRow(_('Authentication:'), auth_widget)

        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        form.addRow(_('Username:'), self.username_edit)
        form.addRow(_('Password:'), self.password_edit)
        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_cancel = QPushButton(_('Cancel'))
        self.btn_save = QPushButton(_('Save'))
        self.btn_save.setDefault(True)
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

        self.rb_none.toggled.connect(self._on_auth_toggled)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save.clicked.connect(self._on_save)

        self._on_auth_toggled()

    def _on_auth_toggled(self):
        basic = self.rb_basic.isChecked()
        self.username_edit.setEnabled(basic)
        self.password_edit.setEnabled(basic)

    def _load(self, server):
        self.name_edit.setText(server.get('name', ''))
        self.url_edit.setText(server.get('url', ''))
        auth = server.get('auth', 'basic')
        if auth == 'basic':
            self.rb_basic.setChecked(True)
        else:
            self.rb_none.setChecked(True)
        self.username_edit.setText(server.get('username', ''))
        self.password_edit.setText(server.get('password', ''))
        self._on_auth_toggled()

    def _on_save(self):
        name = self.name_edit.text().strip()
        url = self.url_edit.text().strip()

        if not name:
            QMessageBox.warning(self, _('Input Error'), _('Please enter a server name.'))
            self.name_edit.setFocus()
            return
        if not url.startswith('http://') and not url.startswith('https://'):
            QMessageBox.warning(self, _('Input Error'),
                                _('URL must start with http:// or https://'))
            self.url_edit.setFocus()
            return

        self.accept()

    def get_server(self) -> dict:
        auth = 'basic' if self.rb_basic.isChecked() else 'none'
        result = {
            'name': self.name_edit.text().strip(),
            'url': self.url_edit.text().strip(),
            'auth': auth,
        }
        if auth == 'basic':
            result['username'] = self.username_edit.text()
            result['password'] = self.password_edit.text()
        return result


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
