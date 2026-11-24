"""Settings dialog (Ctrl+,): capture folders, recording part length, keyboard shortcuts."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from camdesk.config.settings import Settings
from camdesk.ui import strings
from camdesk.ui.theme import tokens
from camdesk.ui.widgets.card import Card
from camdesk.ui.win_frame import dark_title_bar

MIN_PART_MINUTES = 1
MAX_PART_MINUTES = 240


class FolderField(QWidget):
    """[path ..........] [Browse…] [Default]"""

    def __init__(self, current: Path, default: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._default = default
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_2)
        self.edit = QLineEdit(str(current))
        browse = QPushButton(strings.SETTINGS_BROWSE)
        browse.setProperty("variant", "ghost")
        browse.clicked.connect(self._browse)
        reset = QPushButton(strings.SETTINGS_RESET)
        reset.setProperty("variant", "ghost")
        reset.clicked.connect(lambda: self.edit.setText(str(self._default)))
        layout.addWidget(self.edit, 1)
        layout.addWidget(browse)
        layout.addWidget(reset)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, strings.SETTINGS_BROWSE, self.edit.text())
        if folder:
            self.edit.setText(folder)

    def value(self) -> Path:
        return Path(self.edit.text().strip() or str(self._default))


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: Settings,
        default_snapshots: Path,
        default_recordings: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self._defaults = (default_snapshots, default_recordings)
        self.setWindowTitle(strings.SETTINGS_TITLE)
        self.setMinimumWidth(tokens.SETTINGS_DIALOG_WIDTH)
        dark_title_bar(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.SPACE_4, tokens.SPACE_4, tokens.SPACE_4, tokens.SPACE_4)
        layout.setSpacing(tokens.SPACE_3)

        captures = Card(strings.SETTINGS_CAPTURES)
        self.snapshots = FolderField(settings.snapshots_path(), default_snapshots)
        self.recordings = FolderField(settings.recordings_path(), default_recordings)
        for text, field in (
            (strings.SETTINGS_SNAPSHOTS_FOLDER, self.snapshots),
            (strings.SETTINGS_RECORDINGS_FOLDER, self.recordings),
        ):
            label = QLabel(text)
            label.setProperty("role", "label")
            captures.add(label)
            captures.add(field)
        part_row = QWidget()
        pr = QHBoxLayout(part_row)
        pr.setContentsMargins(0, 0, 0, 0)
        pr.addWidget(QLabel(strings.SETTINGS_PART_LENGTH))
        pr.addStretch(1)
        self.part_minutes = QSpinBox()
        self.part_minutes.setRange(MIN_PART_MINUTES, MAX_PART_MINUTES)
        self.part_minutes.setSuffix(strings.SETTINGS_MINUTES)
        self.part_minutes.setValue(settings.segment_minutes)
        pr.addWidget(self.part_minutes)
        captures.add(part_row)
        layout.addWidget(captures)

        shortcuts = Card(strings.SETTINGS_SHORTCUTS)
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(tokens.SPACE_6)
        grid.setVerticalSpacing(tokens.SPACE_1)
        for row, (keys, action) in enumerate(strings.SHORTCUTS):
            key_label = QLabel(keys)
            key_label.setProperty("role", "mono")
            action_label = QLabel(action)
            action_label.setProperty("role", "secondary")
            grid.addWidget(key_label, row, 0)
            grid.addWidget(action_label, row, 1)
        shortcuts.add(grid_widget)
        layout.addWidget(shortcuts)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(strings.SETTINGS_CANCEL)
        cancel.setProperty("variant", "ghost")
        cancel.clicked.connect(self.reject)
        save = QPushButton(strings.SETTINGS_SAVE)
        save.setProperty("variant", "primary")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

    def apply(self) -> None:
        """Copy the form into Settings (default folders are stored as None = "follow default")."""
        s = self.settings
        snaps, recs = self.snapshots.value(), self.recordings.value()
        s.snapshots_dir = None if snaps == self._defaults[0] else str(snaps)
        s.recordings_dir = None if recs == self._defaults[1] else str(recs)
        s.segment_minutes = self.part_minutes.value()
