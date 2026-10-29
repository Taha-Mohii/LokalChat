"""Command-line entry point for LocalChat."""
import queue
import sys
import threading

from config import get_or_create_config, TCP_PORT
from utils.crypto import derive_key, hash_room_code, get_public_key
from core.discovery import Discovery
from core.peer_manager import PeerManager
from core.server import Server
from core.client import Client
from features.chat import Chat
from storage.database import init_db


class LocalChat:
    def __init__(self, name: str, room_code: str):
        self.config = get_or_create_config(name)
        self.name = self.config["name"]
        self.identity_private_key = self.config["identity_private_key"]
        self.public_key = get_public_key(self.identity_private_key)
        self.room_code = room_code
        self.key = derive_key(room_code)
        self.message_queue = queue.Queue()
        init_db()
        self.peer_manager = PeerManager()
        self.client = Client(self.key, self.identity_private_key)
        self.chat = Chat(self.name, self.client, self.peer_manager,
                         hash_room_code(room_code), self.config["device_id"],
                         on_peer_left=lambda ip, peer_name: print(f"{peer_name} left the room"))
        self.server = Server("0.0.0.0", TCP_PORT, self.key,
                             on_message=self._on_message,
                             on_file=lambda ip, path, offer:
                             print(f"Received {offer.get('file')} from {ip}: {path}"),
                             device_id=self.config["device_id"],
                             identity_private_key=self.identity_private_key,
                             peer_identity=self.peer_manager.get_peer)
        self.discovery = Discovery(
            name=self.name, tcp_port=TCP_PORT, room_code=room_code,
            on_peer_found=self._on_peer_found,
            device_id=self.config["device_id"],
            public_key=self.public_key,
            on_peer_left=self._on_peer_left)

    def start(self):
        self.server.start()
        self.discovery.start()
        print(f"[LocalChat] Started as '{self.name}' in room '{self.room_code}'")
        self._input_loop()

    def _on_peer_found(self, ip: str, name: str, port: int, device_id: str = "",
                       public_key: str = ""):
        is_new = not self.peer_manager.is_known(ip)
        self.peer_manager.add_peer(ip, name, port, device_id, public_key)
        if is_new:
            print(f"[LocalChat] {name} joined the room")

    def _on_peer_left(self, ip: str, name: str):
        self.peer_manager.remove_peer(ip)

    def _on_message(self, ip: str, msg: dict):
        self.message_queue.put((ip, msg))
        self._process_messages()

    def _process_messages(self):
        while not self.message_queue.empty():
            ip, msg = self.message_queue.get()
            result = self.chat.receive(ip, msg)
            if result and result.get("type") == "MSG":
                print(self.chat.format_message(result))
            elif result and result.get("type") == "DM":
                print(f"[DM] {self.chat.format_message(result)}")
            elif result and result.get("type") == "PEER_LEFT":
                print(f"[LocalChat] {result['from']} left the room")

    def _input_loop(self):
        print("Type messages and press Enter to send. Ctrl+C to quit.\n")
        try:
            while True:
                text = input()
                if text.strip():
                    print(self.chat.format_message(self.chat.send(text)))
        except (KeyboardInterrupt, EOFError):
            print("\n[LocalChat] Leaving room...")
        finally:
            self.chat.leave()
            self.discovery.stop()
            self.server.stop()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 main.py <your_name> <room_code>")
        sys.exit(1)
    LocalChat(sys.argv[1], sys.argv[2]).start()
