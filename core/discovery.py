import socket
import threading
import json
import os
import struct
import time
import ipaddress
from utils.crypto import hash_room_code

DISCOVERY_PORT = 5001
BROADCAST_ADDR = "255.255.255.255"
HELLO_INTERVAL = 2
PEER_TIMEOUT = 12


def _interface_broadcast_addresses() -> list[str]:
    """Find directed IPv4 broadcasts on Linux; other platforms use limited broadcast."""
    try:
        import fcntl
    except ImportError:
        return []
    addresses = []
    try:
        probe_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError:
        return []
    with probe_socket as probe:
        try:
            interfaces = socket.if_nameindex()
        except OSError:
            return []
        for _, interface in interfaces:
            request = struct.pack("256s", interface.encode("utf-8")[:15])
            try:
                ip_bytes = fcntl.ioctl(probe.fileno(), 0x8915, request)[20:24]
                mask_bytes = fcntl.ioctl(probe.fileno(), 0x891B, request)[20:24]
                ip = ipaddress.IPv4Address(int.from_bytes(ip_bytes, "big"))
                mask = int(ipaddress.IPv4Address(int.from_bytes(mask_bytes, "big")))
                if ip.is_loopback or ip.is_link_local:
                    continue
                broadcast = ipaddress.IPv4Address(int(ip) | (~mask & 0xFFFFFFFF))
                if not broadcast.is_reserved and not broadcast.is_multicast:
                    addresses.append(str(broadcast))
            except (OSError, ValueError):
                continue
    return addresses


class Discovery:
    def __init__(self, name: str, tcp_port: int, room_code: str, on_peer_found,
                 device_id: str = "", on_peer_left=None, broadcast_addr=None,
                 on_error=None, public_key: str = ""):
        """
        name         → this peer's display name
        tcp_port     → port others should connect to for chat/file transfer
        room_code    → the shared room code entered by user
        on_peer_found → callback function called when a new peer is discovered
        """
        self.name = name
        self.tcp_port = tcp_port
        self.room_hash = hash_room_code(room_code)
        self.on_peer_found = on_peer_found
        self.device_id = device_id
        self.public_key = public_key
        self.on_peer_left = on_peer_left or (lambda ip, name: None)
        configured = broadcast_addr or os.environ.get("LOCALCHAT_BROADCAST")
        if configured:
            self.broadcast_addrs = [address.strip() for address in configured.split(",")
                                    if address.strip()]
        else:
            self.broadcast_addrs = list(dict.fromkeys(
                _interface_broadcast_addresses() + [BROADCAST_ADDR]))
        self.on_error = on_error or (lambda message: None)
        self.running = False
        self.known_peers = {}  # ip -> peer info
        self._local_ips = self._get_local_ipv4_addresses()
        self._duplicate_warning_sent = False

    def start(self):
        self.running = True
        threading.Thread(target=self._listen, daemon=True).start()
        threading.Thread(target=self._broadcast_loop, daemon=True).start()

    def stop(self):
        self.running = False

    def _broadcast_loop(self):
        """Repeatedly broadcasts HELLO every few seconds."""
        while self.running:
            self._send_hello()
            time.sleep(HELLO_INTERVAL)

    def _send_hello(self):
        """Sends a HELLO broadcast to the entire local network."""
        msg = json.dumps(
            {
                "type": "HELLO",
                "name": self.name,
                "id": self.device_id,
                "public_key": self.public_key,
                "port": self.tcp_port,
                "room": self.room_hash,
            }
        ).encode()

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                for address in self.broadcast_addrs:
                    try:
                        s.sendto(msg, (address, DISCOVERY_PORT))
                    except OSError as exc:
                        print(f"[Discovery] Broadcast to {address} failed: {exc}")
        except OSError as exc:
            print(f"[Discovery] Broadcast failed: {exc}")

    def _send_ack(self, ip: str):
        """Sends HELLO_ACK directly to a specific peer."""
        msg = json.dumps(
            {
                "type": "HELLO_ACK",
                "name": self.name,
                "id": self.device_id,
                "public_key": self.public_key,
                "port": self.tcp_port,
                "room": self.room_hash,
            }
        ).encode()

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.sendto(msg, (ip, DISCOVERY_PORT))
        except OSError as exc:
            print(f"[Discovery] ACK failed for {ip}: {exc}")

    def _listen(self):
        """Listens for HELLO and HELLO_ACK packets from other peers."""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            try:
                s.bind(("", DISCOVERY_PORT))
            except OSError as exc:
                if self.running:
                    print(f"[Discovery] Could not listen on UDP {DISCOVERY_PORT}: {exc}")
                    self.on_error(f"Could not open discovery port {DISCOVERY_PORT}: {exc}")
                self.running = False
                return
            s.settimeout(1.0)

            while self.running:
                try:
                    data, (ip, _) = s.recvfrom(1024)
                    self._handle_packet(data, ip)
                except socket.timeout:
                    self._expire_peers()
                    continue
                except OSError:
                    if self.running:
                        continue
                    break

    def _handle_packet(self, data: bytes, ip: str):
        """Processes incoming UDP packets."""
        try:
            msg = json.loads(data.decode())
        except Exception:
            return

        # Ignore wrong room
        if msg.get("room") != self.room_hash:
            return

        msg_type = msg.get("type")
        name = msg.get("name")
        port = msg.get("port")
        device_id = msg.get("id")
        public_key = msg.get("public_key", "")

        if not isinstance(name, str) or not isinstance(port, int) or not 1 <= port <= 65535:
            return
        if device_id and device_id == self.device_id:
            if ip not in self._local_ips and not self._duplicate_warning_sent:
                self._duplicate_warning_sent = True
                self.on_error(
                    "Another computer has the same LocalChat identity. Remove config.json on that computer and restart it."
                )
            return

        if msg_type == "HELLO":
            # Someone is announcing themselves — send ACK back
            self._send_ack(ip)
            self._register_peer(ip, name, port, device_id, public_key)

        elif msg_type == "HELLO_ACK":
            # Someone acknowledged our HELLO
            self._register_peer(ip, name, port, device_id, public_key)

    def _register_peer(self, ip: str, name: str, port: int, device_id: str = "",
                       public_key: str = ""):
        """Adds peer to known list and fires callback if new."""
        if ip in ("127.0.0.1", "0.0.0.0") and not device_id:
            return
        first_seen = ip not in self.known_peers
        self.known_peers[ip] = {"name": name, "port": port, "device_id": device_id,
                                "public_key": public_key,
                                "last_seen": time.monotonic()}
        if first_seen:
            print(f"[Discovery] Found peer: {name} at {ip}:{port}")
        self.on_peer_found(ip, name, port, device_id, public_key)

    def _expire_peers(self):
        now = time.monotonic()
        expired = [ip for ip, peer in self.known_peers.items()
                   if now - peer.get("last_seen", now) > PEER_TIMEOUT]
        for ip in expired:
            peer = self.known_peers.pop(ip)
            self.on_peer_left(ip, peer.get("name", ip))

    @staticmethod
    def _get_local_ipv4_addresses() -> set[str]:
        addresses = {"127.0.0.1"}
        try:
            import fcntl
        except ImportError:
            return addresses
        try:
            probe_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except OSError:
            return addresses
        with probe_socket as probe:
            try:
                interfaces = socket.if_nameindex()
            except OSError:
                return addresses
            for _, interface in interfaces:
                request = struct.pack("256s", interface.encode("utf-8")[:15])
                try:
                    raw = fcntl.ioctl(probe.fileno(), 0x8915, request)[20:24]
                    addresses.add(socket.inet_ntoa(raw))
                except OSError:
                    continue
        return addresses
