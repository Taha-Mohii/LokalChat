import socket
import threading
from utils.framing import encode_message
from utils.crypto import encrypt_message, derive_dm_key, get_public_key


class Client:
    def __init__(self, key: bytes, identity_private_key: str = ""):
        """
        key → AES key derived from room code
        """
        self.key = key
        self.identity_private_key = identity_private_key

    def send(self, ip: str, port: int, payload: dict) -> bool:
        """
        Encrypts and sends a message to a specific peer.
        Returns True if successful, False if connection failed.
        """
        try:
            encrypted = encrypt_message(payload, self.key)
            msg = {"payload": encrypted}
            data = encode_message(msg)

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5.0)
                s.connect((ip, port))
                s.sendall(data)
            return True

        except Exception as e:
            print(f"[Client] Failed to send to {ip}:{port} — {e}")
            return False

    def broadcast(self, peers: dict, payload: dict):
        """
        Sends a message to all known peers.
        peers → dict from PeerManager.get_peers()
        """
        for ip, info in peers.items():
            threading.Thread(target=self.send, args=(ip, info["port"], payload),
                             daemon=True).start()

    def send_dm(self, ip: str, port: int, payload: dict,
                sender_id: str, recipient_id: str, recipient_public_key: str) -> bool:
        try:
            if not self.identity_private_key or not recipient_public_key:
                raise ValueError("Peer encryption keys are unavailable")
            key = derive_dm_key(self.key, self.identity_private_key, recipient_public_key)
            packet = {"dm": True, "from_id": sender_id, "to_id": recipient_id,
                      "from_public_key": get_public_key(self.identity_private_key),
                      "payload": encrypt_message(payload, key)}
            with socket.create_connection((ip, port), timeout=5) as conn:
                conn.sendall(encode_message(packet))
            return True
        except (OSError, ValueError) as exc:
            print(f"[Client] Failed to send direct message to {ip}:{port} — {exc}")
            return False

    def send_file(self, ip: str, port: int, filepath: str, key: bytes,
                  dm: bool = False, recipient_id: str = "",
                  sender_id: str = "", recipient_public_key: str = "") -> bool:
        from features.file_transfer import send_file
        return send_file(ip, port, filepath, key, dm, recipient_id, sender_id,
                         self.identity_private_key, recipient_public_key)
