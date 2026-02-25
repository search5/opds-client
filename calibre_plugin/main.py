import os

from calibre.gui2.actions import InterfaceAction

from .dialog import OPDSDialog


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
