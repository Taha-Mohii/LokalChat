import time
from features.protocol import make_msg, make_bye, make_dm
from core.client import Client
from core.peer_manager import PeerManager
from storage.database import save_message


class Chat:
    def __init__(self, name: str, client: Client, peer_manager: PeerManager,
                 room_id: str, device_id: str, on_peer_left=None):
        self.name, self.client, self.peer_manager = name, client, peer_manager
        self.room_id, self.device_id = room_id, device_id
        self.on_peer_left = on_peer_left or (lambda ip, name: None)
        self.history = []

    def _store(self, msg: dict, kind="GROUP", to_id=""):
        save_message(self.room_id, msg.get("from_id", self.device_id),
                     msg.get("from", self.name), msg.get("text", ""),
                     int(msg.get("timestamp", time.time())), kind, to_id)
        self.history.append(msg)

    def send(self, text: str):
        msg = make_msg(self.name, text)
        msg["from_id"] = self.device_id
        self._store(msg)
        self.client.broadcast(self.peer_manager.get_peers(), msg)
        return msg

    def receive(self, ip: str, msg: dict):
        msg_type = msg.get("type")
        if msg_type == "MSG":
            self._store(msg)
            return msg
        if msg_type == "DM":
            if msg.get("to") != self.device_id:
                return None
            peer = self.peer_manager.get_peer(ip)
            msg["from_id"] = (peer or {}).get("device_id", ip)
            self._store(msg, "DM", self.device_id)
            return msg
        if msg_type == "BYE":
            peer = self.peer_manager.get_peer(ip)
            peer_name = (peer or {}).get("name", msg.get("from", ip))
            self.on_peer_left(ip, peer_name)
            return {"type": "PEER_LEFT", "from": peer_name}
        return None

    def leave(self):
        self.client.broadcast(self.peer_manager.get_peers(), make_bye(self.name))

    def get_history(self) -> list:
        return list(self.history)

    def format_message(self, msg: dict) -> str:
        ts = time.strftime("%H:%M", time.localtime(msg.get("timestamp", 0)))
        return f"[{ts}] {msg.get('from', 'unknown')}: {msg.get('text', '')}"

    def send_to_peer(self, ip: str, port: int, text: str) -> dict | None:
        peer = self.peer_manager.get_peer(ip)
        if not peer:
            return None
        msg = make_dm(self.name, text, peer.get("device_id", ip))
        msg["from_id"] = self.device_id
        if self.client.send_dm(ip, port, msg, self.device_id,
                               peer.get("device_id", ip), peer.get("public_key", "")):
            self._store(msg, "DM", peer.get("device_id", ip))
            return msg
        return None
