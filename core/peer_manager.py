import threading

class PeerManager:
    def __init__(self):
        """
        Stores all active peers.
        Uses a lock because multiple threads may add/remove peers at the same time.
        """
        
        self._peers = {}
        self._lock = threading.Lock()
        
    def add_peer(self, ip: str, name:str, port:int, device_id: str | None = None,
                 public_key: str = ""):
        """Add or update a peer."""
        with self._lock:
            is_new = ip not in self._peers
            self._peers[ip] = {"name": name, "port": port,
                               "device_id": device_id or ip,
                               "public_key": public_key}
            if is_new:
                print(f"[PeerManager] Added peer: {name} at {ip}:{port}")

    def remove_peer(self, ip: str):
        """Remove a peer by IP."""
        with self._lock:
            peer = self._peers.pop(ip,None)
            if peer:
                print(f"[PeerManager] Removed peer: {peer['name']} at {ip}")

    
    def get_peers(self) -> dict:
        """Returns a copy of the current peer list."""
        with self._lock:
            return dict(self._peers)

    def get_peer(self, ip: str) -> dict | None:
        """Returns info for a specific peer."""
        with self._lock:
            peer = self._peers.get(ip)
            return dict(peer) if peer else None

    def is_known(self, ip: str) -> bool:
        """Check if a peer is already registered."""
        with self._lock:
            return ip in self._peers

    def clear(self):
        """Remove all peers — used on disconnect/shutdown."""
        with self._lock:
            self._peers.clear()
            print("[PeerManager] All peers cleared")
