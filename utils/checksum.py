import hashlib


def get_checksum(filepath: str, chunk_size: int = 4096) -> str:
    """Returns SHA-256 checksum of a file as a hex string."""
    digest = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
