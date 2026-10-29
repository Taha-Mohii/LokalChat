import os
import json
import hmac
import hashlib
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


APP_SALT = b"localchat_v1_salt_2024"


def derive_key(room_code: str) -> bytes:
    """
    Turns room code like "482901" into a 256 bit AES key.
    Every peer with same room code gets identical key.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,            # 256 bit key
        salt=APP_SALT,
        iterations=200_000,
    )
    return kdf.derive(room_code.upper().encode())


def hash_room_code(room_code: str) -> str:
    """
    One way hash of room code for HELLO discovery packets.
    Peers verify they are in same room without exposing actual code.
    """
    h = hmac.new(APP_SALT, room_code.upper().encode(), hashlib.sha256)
    return h.hexdigest()[:16]


def create_identity() -> tuple[str, str]:
    """Create a persistent X25519 key pair and return base64 private/public keys."""
    private_key = X25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    public_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(private_bytes).decode(), base64.b64encode(public_bytes).decode()


def get_public_key(private_key_b64: str) -> str:
    private_bytes = base64.b64decode(private_key_b64, validate=True)
    private_key = X25519PrivateKey.from_private_bytes(private_bytes)
    public_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(public_bytes).decode()


def derive_dm_key(room_key: bytes, private_key_b64: str, peer_public_key_b64: str) -> bytes:
    """Derive an authenticated-encryption key from the two peers' X25519 keys."""
    private_bytes = base64.b64decode(private_key_b64, validate=True)
    public_bytes = base64.b64decode(peer_public_key_b64, validate=True)
    private_key = X25519PrivateKey.from_private_bytes(private_bytes)
    peer_public_key = X25519PublicKey.from_public_bytes(public_bytes)
    shared_secret = private_key.exchange(peer_public_key)
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=room_key,
                info=b"localchat-dm-v1").derive(shared_secret)


def encrypt_message(payload: dict, key: bytes) -> str:
    """
    Encrypts a dict with AES-GCM.
    Returns base64 string safe to put inside JSON.
    """
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)       # random 12 bytes, unique per message
    plaintext = json.dumps(payload).encode()
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_message(encrypted_b64: str, key: bytes) -> dict | None:
    """
    Decrypts a base64 AES-GCM payload back to dict.
    Returns None if decryption fails — wrong key or tampered packet.
    """
    try:
        raw = base64.b64decode(encrypted_b64)
        nonce = raw[:12]
        ciphertext = raw[12:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return json.loads(plaintext.decode())
    except Exception:
        return None 
