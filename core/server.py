import socket
import threading

from features.file_transfer import receive_file
from utils.crypto import decrypt_message, encrypt_message, derive_dm_key
from utils.framing import decode_message, encode_message


class Server:
    def __init__(self, host: str, port: int, key: bytes, on_message,
                 on_file=None, device_id: str = "", identity_private_key: str = "",
                 peer_identity=None, on_error=None):
        self.host, self.port, self.key = host, port, key
        self.on_message = on_message
        self.on_file = on_file or (lambda ip, path, offer: None)
        self.device_id = device_id
        self.identity_private_key = identity_private_key
        self.peer_identity = peer_identity or (lambda ip: None)
        self.on_error = on_error or (lambda message: None)
        self.running = False
        self._socket = None

    def start(self):
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def stop(self):
        self.running = False
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass

    def _accept_loop(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            self._socket = server
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server.bind((self.host, self.port))
                server.listen(32)
            except OSError as exc:
                self.running = False
                print(f"[Server] Could not listen on {self.host}:{self.port}: {exc}")
                self.on_error(f"Could not open the chat port {self.port}: {exc}")
                return
            server.settimeout(1.0)
            print(f"[Server] Listening on {self.host}:{self.port}")
            while self.running:
                try:
                    conn, (ip, _) = server.accept()
                    threading.Thread(target=self._handle_peer,
                                     args=(conn, ip), daemon=True).start()
                except socket.timeout:
                    continue
                except OSError:
                    if self.running:
                        continue
                    break
            self._socket = None

    def _handle_peer(self, conn: socket.socket, ip: str):
        with conn:
            conn.settimeout(120)
            raw = decode_message(conn)
            if raw is None:
                return
            active_key = self.key
            if raw.get("dm"):
                sender_id, recipient_id = raw.get("from_id"), raw.get("to_id")
                sender_public_key = raw.get("from_public_key")
                if (not isinstance(sender_id, str) or not isinstance(recipient_id, str)
                        or not isinstance(sender_public_key, str)):
                    return
                peer = self.peer_identity(ip)
                if (not peer or peer.get("device_id") != sender_id
                        or peer.get("public_key") != sender_public_key):
                    return
                try:
                    active_key = derive_dm_key(self.key, self.identity_private_key,
                                               sender_public_key)
                except (ValueError, TypeError):
                    return
                if recipient_id != self.device_id:
                    if raw.get("file"):
                        result = {"type": "FILE_RESULT", "ok": False,
                                  "error": "This file was addressed to another peer"}
                        conn.sendall(encode_message({"payload": encrypt_message(result, active_key)}))
                    return
            msg = decrypt_message(raw.get("payload", ""), active_key)
            if msg is None:
                print(f"[Server] Bad decrypt from {ip} — ignored")
                return
            if raw.get("dm") and (msg.get("type") != "DM"
                    and msg.get("type") != "FILE_OFFER"):
                return
            if raw.get("dm") and (msg.get("from_id") != raw.get("from_id")
                    or msg.get("to") != raw.get("to_id")):
                return
            if msg.get("type") == "FILE_OFFER":
                path = receive_file(conn, active_key, msg)
                conn.sendall(encode_message({"payload": encrypt_message(
                    {"type": "FILE_RESULT", "ok": bool(path),
                     "file": msg.get("file"),
                     "error": None if path else "File transfer or checksum verification failed"},
                    active_key)}))
                if path:
                    self.on_file(ip, path, msg)
                return
            self.on_message(ip, msg)
