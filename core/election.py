import threading


class Election:
    """Deterministic local host choice using advertised device IDs."""
    def __init__(self, device_id: str, peer_manager, client, on_elected,
                 on_change=None):
        self.device_id = device_id
        self.peer_manager = peer_manager
        self.client = client
        self.on_elected = on_elected
        self.on_change = on_change or (lambda host_id: None)
        self.is_host = False
        self.host_id = ""
        self._lock = threading.Lock()

    def run(self):
        peers = self.peer_manager.get_peers()
        ids = [p.get("device_id") for p in peers.values() if p.get("device_id")]
        chosen = self.device_id == max([self.device_id] + ids)
        with self._lock:
            changed_to_host = chosen and not self.is_host
            changed = self.host_id != max([self.device_id] + ids)
            self.is_host = chosen
            self.host_id = max([self.device_id] + ids)
        if changed_to_host:
            self.on_elected()
        if changed:
            self.on_change(self.host_id)

    def _become_host(self):
        self.run()

    def is_current_host(self) -> bool:
        return self.is_host

    def reset(self):
        with self._lock:
            self.is_host = False
        self.run()
