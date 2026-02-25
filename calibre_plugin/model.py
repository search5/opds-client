from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex

load_translations()

COLUMNS = [_('Title'), _('Author'), _('Format'), _('Size')]


def _fmt_size(total_bytes: int) -> str:
    if total_bytes <= 0:
        return ''
    if total_bytes >= 1024 * 1024:
        return '%.1fMB' % (total_bytes / (1024 * 1024))
    if total_bytes >= 1024:
        return '%.1fKB' % (total_bytes / 1024)
    return '%dB' % total_bytes


class BookTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = []

    def set_entries(self, entries):
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def entry(self, row):
        return self._entries[row]

    def rowCount(self, parent=QModelIndex()):
        return len(self._entries)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        entry = self._entries[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0:
                return entry.title
            if col == 1:
                return ', '.join(entry.authors) if entry.authors else ''
            if col == 2:
                return ', '.join(f['type'].upper() for f in entry.formats) if entry.formats else ''
            if col == 3:
                total = sum(f.get('size', 0) for f in entry.formats)
                return _fmt_size(total)

        if role == Qt.UserRole:
            return entry

        return None
