import os
import sys
import threading
import time
from pathlib import Path

# Support both `python -m ui.app` and `python ui/app.py` launches.
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt5.QtCore import QObject, pyqtSignal, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QStackedWidget, QDesktopWidget, QMessageBox

from config import get_or_create_config, TCP_PORT, DOWNLOAD_DIR
from utils.crypto import derive_key, hash_room_code, get_public_key
from storage.database import init_db, get_messages
from core.discovery import Discovery
from core.peer_manager import PeerManager
from core.server import Server
from core.client import Client
from core.election import Election
from features.chat import Chat
from ui.launch_screen import LaunchScreen
from ui.chat_screen import ChatScreen


class MainWindow(QStackedWidget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def closeEvent(self, event):
        self.owner._shutdown()
        for dm in list(self.owner.dm_screens.values()):
            dm.close()
        event.accept()


class App(QObject):
    network_message = pyqtSignal(str, object)
    peer_found = pyqtSignal(str, str, int, str, str)
    peer_left = pyqtSignal(str, str)
    file_received = pyqtSignal(str, str, object)
    file_sent = pyqtSignal(str, str, bool, bool)
    network_error = pyqtSignal(str)
    host_changed = pyqtSignal(str)
    dm_sent = pyqtSignal(str, object)

    def __init__(self):
        super().__init__()
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        self.qt_app = QApplication(sys.argv)
        self.window = MainWindow(self)
        self.window.setWindowTitle("LocalChat")
        self.window.setStyleSheet("background-color: #1e1e2e;")
        self.dm_screens = {}
        self.chat_engine = self.chat_screen = None
        self.server = self.discovery = None
        self.peer_manager = None
        self._shutting_down = False
        self.network_message.connect(self._on_message, Qt.QueuedConnection)
        self.peer_found.connect(self._on_peer_found, Qt.QueuedConnection)
        self.peer_left.connect(self._on_peer_left, Qt.QueuedConnection)
        self.file_received.connect(self._on_file_received, Qt.QueuedConnection)
        self.file_sent.connect(self._on_file_sent, Qt.QueuedConnection)
        self.network_error.connect(self._on_network_error, Qt.QueuedConnection)
        self.host_changed.connect(self._on_host_changed, Qt.QueuedConnection)
        self.dm_sent.connect(self._on_dm_sent, Qt.QueuedConnection)
        self.qt_app.aboutToQuit.connect(self._shutdown)
        self._show_launch()
        self.window.resize(1200, 800)
        self.window.show()
        self._center_window()
        self.qt_app.exec_()

    def _center_window(self):
        screen = QDesktopWidget().availableGeometry()
        self.window.move((screen.width() - self.window.width()) // 2,
                         (screen.height() - self.window.height()) // 2)

    def _show_launch(self):
        launch = LaunchScreen(on_join=self._on_join)
        self.window.addWidget(launch)
        self.window.setCurrentWidget(launch)

    def _on_join(self, name: str, room_code: str):
        if self.server and self.server.running:
            return
        config = get_or_create_config(name)
        init_db()
        self.current_room_code = room_code
        self.room_id = hash_room_code(room_code)
        self.device_id = config["device_id"]
        self.identity_private_key = config["identity_private_key"]
        self.public_key = get_public_key(self.identity_private_key)
        self.key = derive_key(room_code)
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        self.peer_manager = PeerManager()
        self.client = Client(self.key, self.identity_private_key)
        self.chat_engine = Chat(name, self.client, self.peer_manager,
                                self.room_id, self.device_id,
                                on_peer_left=lambda ip, peer_name:
                                self.peer_left.emit(ip, peer_name))
        self.server = Server("0.0.0.0", TCP_PORT, self.key,
                             on_message=lambda ip, msg: self.network_message.emit(ip, msg),
                             on_file=lambda ip, path, offer:
                             self.file_received.emit(ip, path, offer),
                             device_id=self.device_id,
                             identity_private_key=self.identity_private_key,
                             peer_identity=self.peer_manager.get_peer,
                             on_error=self.network_error.emit)
        self.discovery = Discovery(name, TCP_PORT, room_code,
                                   on_peer_found=lambda ip, peer_name, port, peer_id, peer_public_key:
                                   self.peer_found.emit(ip, peer_name, port, peer_id or "",
                                                        peer_public_key or ""),
                                   device_id=self.device_id,
                                   public_key=self.public_key,
                                   on_peer_left=lambda ip, peer_name:
                                   self.peer_left.emit(ip, peer_name),
                                   on_error=self.network_error.emit)

        self.election = Election(self.device_id, self.peer_manager, self.client,
                                 on_elected=self._on_elected,
                                 on_change=self.host_changed.emit)
        self.server.start()
        self.discovery.start()
        self.election_timer = threading.Timer(1.0, self.election.run)
        self.election_timer.daemon = True
        self.election_timer.start()
        self.chat_screen = ChatScreen(name, room_code, self._send_message,
                                      self._send_file, self._open_dm)
        self.window.addWidget(self.chat_screen)
        self.window.setCurrentWidget(self.chat_screen)
        self.window.setMinimumSize(900, 650)
        QTimer.singleShot(8000, self._report_no_peers)

        for message in get_messages(self.room_id, kind="GROUP"):
            self._show_group_message(message, message.get("from_id") == self.device_id)

    def _on_message(self, ip: str, msg: dict):
        dm_was_open = ip in self.dm_screens
        result = self.chat_engine.receive(ip, msg)
        if not result:
            return
        if result.get("type") == "MSG":
            self._show_group_message(result)
        elif result.get("type") == "DM":
            peer = self.peer_manager.get_peer(ip) or {}
            dm = self._ensure_dm(ip, peer.get("name", result.get("from", "Peer")))
            if dm_was_open:
                ts = self._format_time(result)
                dm.add_message(result.get("from", "unknown"), result.get("text", ""), ts)
            if self.chat_screen:
                self.chat_screen.add_notification(f"Direct message from {result.get('from', 'peer')}")
            dm.show()
            dm.raise_()
            dm.activateWindow()
        elif result.get("type") == "PEER_LEFT":
            return

    def _format_time(self, msg):
        return time.strftime("%H:%M", time.localtime(msg.get("timestamp", 0)))

    def _show_group_message(self, msg, is_self=False):
        if self.chat_screen:
            self.chat_screen.add_message(msg.get("from", "unknown"),
                                         msg.get("text", ""), self._format_time(msg), is_self)

    def _on_peer_found(self, ip: str, name: str, port: int, device_id: str,
                       public_key: str):
        is_new = not self.peer_manager.is_known(ip)
        self.peer_manager.add_peer(ip, name, port, device_id, public_key)
        if not self.chat_screen:
            return
        peers = self.peer_manager.get_peers()
        self.chat_screen.update_peers(len(peers))
        self.chat_screen.add_peer(ip, name)
        if is_new:
            self.chat_screen.add_notification(f"{name} joined the room")
        self.election.run()

    def _report_no_peers(self):
        if self.chat_screen and not self.peer_manager.get_peers():
            self.chat_screen.add_notification(
                "Still searching: both devices need the same room code and Wi-Fi. "
                "Check that UDP 5001 and TCP 5000 are allowed through the firewall."
            )

    def _on_peer_left(self, ip: str, name: str):
        if self.peer_manager and not self.peer_manager.is_known(ip):
            return
        if self.peer_manager:
            self.peer_manager.remove_peer(ip)
        if self.chat_screen:
            self.chat_screen.remove_peer(ip)
            self.chat_screen.update_peers(len(self.peer_manager.get_peers()))
            self.chat_screen.add_notification(f"{name} left the room")
        dm = self.dm_screens.pop(ip, None)
        if dm:
            dm.close()
        if hasattr(self, "election"):
            self.election.run()

    def _on_file_received(self, ip: str, path: str, offer: dict):
        peer = self.peer_manager.get_peer(ip) or {}
        sender = peer.get("name", ip)
        filename = os.path.basename(path)
        if offer.get("dm"):
            dm = self._ensure_dm(ip, sender)
            dm.add_message(sender, f"Received file: {filename}",
                           self._format_time({"timestamp": time.time()}))
            dm.show()
            dm.raise_()
            dm.activateWindow()
            return
        if self.chat_screen:
            self.chat_screen.add_notification(f"{sender} sent {filename}; saved to Downloads")

    def _on_file_sent(self, ip: str, filepath: str, is_dm: bool, success: bool):
        filename = os.path.basename(filepath)
        peer = self.peer_manager.get_peer(ip) or {"name": ip}
        if not success:
            note = f"Could not send {filename} to {peer['name']}"
            if is_dm and ip in self.dm_screens:
                self.dm_screens[ip].add_message("LocalChat", note,
                                                self._format_time({"timestamp": time.time()}))
            elif self.chat_screen:
                self.chat_screen.add_notification(note)
            return
        if is_dm:
            dm = self.dm_screens.get(ip)
            if dm:
                dm.add_message(self.chat_engine.name, f"Sent file: {filename}",
                               self._format_time({"timestamp": time.time()}), is_self=True)
        elif self.chat_screen:
            self.chat_screen.add_notification(f"Sent {filename} to room peers")

    def _on_network_error(self, message: str):
        if self.chat_screen:
            self.chat_screen.add_notification(message)
        else:
            QMessageBox.warning(self.window, "LocalChat network error", message)

    def _on_elected(self):
        if self.election.is_host:
            print("[App] This peer is the host")

    def _on_host_changed(self, host_id: str):
        if not self.chat_screen:
            return
        if host_id == self.device_id:
            self.chat_screen.set_host("You are host", is_self=True)
            return
        peer = next((info for info in self.peer_manager.get_peers().values()
                     if info.get("device_id") == host_id), None)
        self.chat_screen.set_host(f"Host: {peer['name']}" if peer else "Host elected",
                                  is_self=False)

    def _ensure_dm(self, ip: str, peer_name: str):
        from ui.dm_screen import DMScreen
        dm = self.dm_screens.get(ip)
        if dm:
            return dm
        dm = DMScreen(self.chat_engine.name, peer_name, ip,
                      on_send=self._send_dm,
                      on_send_file=lambda peer_ip, path: self._send_dm_file(peer_ip, path))
        self.dm_screens[ip] = dm
        peer = self.peer_manager.get_peer(ip) or {}
        participant_id = peer.get("device_id", ip)
        for message in get_messages(self.room_id, kind="DM", participant_id=participant_id):
            dm.add_message(message["from_name"], message["text"], self._format_time(message),
                           is_self=message.get("from_id") == self.device_id)
        return dm

    def _open_dm(self, ip: str, peer_name: str):
        dm = self._ensure_dm(ip, peer_name)
        dm.show()
        dm.raise_()
        dm.activateWindow()

    def _send_dm(self, ip: str, text: str):
        threading.Thread(target=self._send_dm_worker, args=(ip, text), daemon=True).start()

    def _send_dm_worker(self, ip: str, text: str):
        peer = self.peer_manager.get_peer(ip)
        if peer:
            msg = self.chat_engine.send_to_peer(ip, peer["port"], text)
            self.dm_sent.emit(ip, {"peer_name": peer["name"], "message": msg})

    def _on_dm_sent(self, ip: str, result: dict):
        msg = result.get("message")
        dm = self._ensure_dm(ip, result.get("peer_name", "Peer"))
        if msg:
            dm.add_message(msg["from"], msg["text"], self._format_time(msg), is_self=True)
        else:
            dm.add_message("LocalChat", "Message could not be sent", self._format_time({"timestamp": time.time()}))

    def _send_message(self, text: str):
        msg = self.chat_engine.send(text)
        self._show_group_message(msg, is_self=True)
        if not self.peer_manager.get_peers() and self.chat_screen:
            self.chat_screen.add_notification(
                "Only you are in this room right now; this message was not delivered to anyone."
            )

    def _send_file(self, filepath: str):
        peers = self.peer_manager.get_peers()
        if not peers:
            if self.chat_screen:
                self.chat_screen.add_notification(
                    "No peers are connected, so the file could not be shared. Check that both devices joined the same room and Wi-Fi."
                )
            return
        for ip, info in peers.items():
            threading.Thread(target=self._send_file_to_peer,
                             args=(ip, info, filepath, False), daemon=True).start()

    def _send_dm_file(self, ip: str, filepath: str):
        peer = self.peer_manager.get_peer(ip)
        if peer:
            threading.Thread(target=self._send_file_to_peer,
                             args=(ip, peer, filepath, True), daemon=True).start()

    def _send_file_to_peer(self, ip, peer, filepath, is_dm):
        recipient_id = peer.get("device_id", "") if is_dm else ""
        ok = self.client.send_file(ip, peer["port"], filepath, self.key,
                                   is_dm, recipient_id, self.device_id,
                                   peer.get("public_key", ""))
        self.file_sent.emit(ip, filepath, is_dm, ok)

    def _shutdown(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        if hasattr(self, "election_timer"):
            self.election_timer.cancel()
        if self.chat_engine:
            threading.Thread(target=self.chat_engine.leave, daemon=True).start()
        if self.discovery:
            self.discovery.stop()
        if self.server:
            self.server.stop()


if __name__ == "__main__":
    App()
