from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QRadioButton,
    QButtonGroup, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QMessageBox,
)
from PyQt5.QtCore import Qt

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
