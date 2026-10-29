"""Encrypted-metadata, length-bounded file transfer over TCP."""
import os
import re
import socket
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config import CHUNK_SIZE, DOWNLOAD_DIR
from utils.crypto import encrypt_message, decrypt_message, derive_dm_key, get_public_key
from utils.framing import encode_message, decode_message, _recv_exact
from utils.checksum import get_checksum

MAX_FILE_SIZE = 1024 * 1024 * 1024


def send_file(ip: str, port: int, filepath: str, key: bytes,
              dm: bool = False, recipient_id: str = "",
              sender_id: str = "", identity_private_key: str = "",
              recipient_public_key: str = "") -> bool:
    """Send one file to one peer using an encrypted offer and exact byte count."""
    if not os.path.isfile(filepath):
        return False
    filename = os.path.basename(filepath)
    size = os.path.getsize(filepath)
    if size > MAX_FILE_SIZE:
        print(f"[FileTransfer] File exceeds the {MAX_FILE_SIZE} byte limit")
        return False
    offer = {"type": "FILE_OFFER", "file": filename, "size": size,
             "checksum": get_checksum(filepath), "dm": dm, "to": recipient_id,
             "from_id": sender_id}
    try:
        transfer_key = derive_dm_key(key, identity_private_key,
                                     recipient_public_key) if dm else key
        aesgcm = AESGCM(transfer_key)
        with socket.create_connection((ip, port), timeout=15) as conn:
            conn.settimeout(30)
            packet = {"payload": encrypt_message(offer, transfer_key)}
            if dm:
                packet.update({"file": True, "dm": True, "from_id": sender_id,
                               "to_id": recipient_id,
                               "from_public_key": get_public_key(identity_private_key)})
            conn.sendall(encode_message(packet))
            with open(filepath, "rb") as source:
                for index, chunk in enumerate(iter(lambda: source.read(CHUNK_SIZE), b"")):
                    nonce = os.urandom(12)
                    aad = _chunk_aad(filename, size, offer["checksum"], index)
                    encrypted = nonce + aesgcm.encrypt(nonce, chunk, aad)
                    conn.sendall(len(encrypted).to_bytes(4, "big") + encrypted)
            raw_result = decode_message(conn)
            result = decrypt_message((raw_result or {}).get("payload", ""), transfer_key)
            if not result or result.get("type") != "FILE_RESULT" or not result.get("ok"):
                raise OSError((result or {}).get("error", "Receiver did not confirm the file"))
        return True
    except Exception as exc:
        print(f"[FileTransfer] Send to {ip} failed: {exc}")
        return False


def receive_file(conn: socket.socket, key: bytes, offer: dict) -> str | None:
    """Receive an offered file; return its saved path after SHA-256 verification."""
    filename = os.path.basename(str(offer.get("file", ""))).strip()
    size = offer.get("size")
    checksum = offer.get("checksum")
    if (not filename or filename in (".", "..") or "\x00" in filename
            or len(filename) > 240 or not isinstance(size, int)
            or size < 0 or size > MAX_FILE_SIZE
            or not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum)):
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    base, ext = os.path.splitext(filename)
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    suffix = 1
    while os.path.exists(filepath):
        filepath = os.path.join(DOWNLOAD_DIR, f"{base} ({suffix}){ext}")
        suffix += 1
    temp_path = filepath + ".part"
    try:
        aesgcm = AESGCM(key)
        with open(temp_path, "wb") as target:
            remaining = size
            index = 0
            while remaining:
                header = _recv_exact(conn, 4)
                if header is None:
                    raise ConnectionError("connection ended before file was complete")
                encrypted_size = int.from_bytes(header, "big")
                if not 28 < encrypted_size <= CHUNK_SIZE + 28:
                    raise ValueError("invalid encrypted chunk size")
                encrypted = _recv_exact(conn, encrypted_size)
                if encrypted is None:
                    raise ConnectionError("connection ended inside an encrypted chunk")
                nonce, ciphertext = encrypted[:12], encrypted[12:]
                chunk = aesgcm.decrypt(nonce, ciphertext,
                                       _chunk_aad(filename, size, checksum, index))
                if not chunk or len(chunk) > remaining:
                    raise ValueError("invalid plaintext chunk size")
                target.write(chunk)
                remaining -= len(chunk)
                index += 1
        if get_checksum(temp_path) != checksum:
            raise ValueError("SHA-256 checksum mismatch")
        os.replace(temp_path, filepath)
        return filepath
    except Exception as exc:
        print(f"[FileTransfer] Receive failed: {exc}")
        try:
            os.remove(temp_path)
        except OSError:
            pass
        return None
def _chunk_aad(filename: str, size: int, checksum: str, index: int) -> bytes:
    return f"{filename}\0{size}\0{checksum}\0{index}".encode("utf-8")
