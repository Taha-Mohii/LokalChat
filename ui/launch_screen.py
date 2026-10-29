from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QDesktopWidget,
    QSizePolicy,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class LaunchScreen(QWidget):
    def __init__(self, on_join):
        super().__init__()
        self.on_join = on_join
        self._build_ui()

    def _build_ui(self):
        self.setWindowTitle("LocalChat")
        self.setStyleSheet("background-color: #1e1e2e;")

        # Outer layout to center the card
        outer = QVBoxLayout()
        outer.setAlignment(Qt.AlignCenter)
        outer.setContentsMargins(0, 0, 0, 0)

        # Card widget
        card = QWidget()
        card.setFixedWidth(500)
        card.setStyleSheet("""
            QWidget {
                background-color: #181825;
                border-radius: 12px;
            }
        """)

        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(32, 32, 32, 32)
        card_layout.setSpacing(14)

        # Title
        title = QLabel("LocalChat")
        title.setFont(QFont("Arial", 22, QFont.Bold))
        title.setStyleSheet("color: #cdd6f4; background: transparent;")
        title.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Offline P2P Chat & File Sharing")
        subtitle.setFont(QFont("Arial", 9))
        subtitle.setStyleSheet("color: #6c7086; background: transparent;")
        subtitle.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(subtitle)

        card_layout.addSpacing(8)

        # Name input
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Your name")
        self.name_input.setMaxLength(32)
        self.name_input.setFixedHeight(52)
        self.name_input.setStyleSheet(self._input_style())
        card_layout.addWidget(self.name_input)

        # Room code input
        self.room_input = QLineEdit()
        self.room_input.setPlaceholderText("Room code (e.g. 482901)")
        self.room_input.setMaxLength(20)
        self.room_input.setFixedHeight(52)
        self.room_input.setStyleSheet(self._input_style())
        self.room_input.returnPressed.connect(self._on_join_clicked)
        card_layout.addWidget(self.room_input)

        card_layout.addSpacing(4)

        # Join button
        join_btn = QPushButton("Join Room")
        join_btn.setFixedHeight(54)
        join_btn.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa;
                color: #1e1e2e;
                border-radius: 8px;
                font-size: 15pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #b4befe;
            }
            QPushButton:pressed {
                background-color: #74c7ec;
            }
        """)
        join_btn.setCursor(Qt.PointingHandCursor)
        join_btn.clicked.connect(self._on_join_clicked)
        card_layout.addWidget(join_btn)

        card.setLayout(card_layout)
        outer.addWidget(card)
        self.setLayout(outer)
        self.name_input.setFocus()

    def _input_style(self):
        return """
            QLineEdit {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 15pt;
            }
            QLineEdit:focus {
                border: 1px solid #89b4fa;
            }
        """

    def _on_join_clicked(self):
        name = self.name_input.text().strip()
        room = self.room_input.text().strip()

        if not name:
            QMessageBox.warning(self, "Error", "Please enter your name.")
            self.name_input.setFocus()
            return

        if not room:
            QMessageBox.warning(self, "Error", "Please enter a room code.")
            self.room_input.setFocus()
            return

        self.on_join(name, room)
