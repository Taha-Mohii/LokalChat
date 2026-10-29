# LokalChat

> Offline peer-to-peer chat and file sharing for devices on the same local network.


<img width="3072" height="1582" alt="image" src="https://github.com/user-attachments/assets/ce397c1c-209a-4f18-ad7b-a3fa42451560" />


## Overview

LokalChat lets people on the same Wi-Fi or LAN exchange messages and files without an internet connection or central chat server. Each running app discovers other peers on the network and connects directly to them.

**Project status:** [In progress / College project / Complete]  
**Author:** [Your name]  
**Course or institution:** [Optional]

## Features

- Group chat in shared rooms
- Direct messages between peers
- File sharing with transfer verification
- Peer list, join and leave notifications
- Local message history stored in SQLite
- Host election when peers join or leave
- Encryption for messages and file transfers

## Requirements

- Python 3.10 or newer
- Wi-Fi or LAN connection between the participating devices
- Inbound network access for TCP port `5000` and UDP port `5001`

## Installation

Clone the repository:

```bash
git clone https://github.com/Taha-Mohii/LokalChat.git
cd LokalChat
```

Create and activate a virtual environment.

**Linux or macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows PowerShell:**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

## Run the graphical app

From the project directory, run:

```bash
python ui/app.py
```

Enter a display name and a room code. Everyone who wants to join the room must use the same room code.

Each computer creates its own local `config.json` identity the first time it runs. Do not copy this file between computers.

## Run the command-line app

```bash
python main.py "Your Name" "your-room-code"
```

The command-line version supports basic group messaging.

## Using LokalChat

1. Connect each device to the same Wi-Fi or LAN.
2. Start LokalChat on each device.
3. Enter the same room code on each device.
4. Wait for peers to appear in the peer list.
5. Send a group message, open a peer’s **DM**, or choose **Share file**.

Received files are saved in the project’s `downloads/` folder. Local message history is stored in `storage/localchat.db`.

## Network setup

LokalChat uses:

| Port | Protocol | Purpose |
|---|---|---|
| 5000 | TCP | Messages and file transfers |
| 5001 | UDP | Peer discovery |

Allow these ports through the firewall on each device. Some guest Wi-Fi networks block communication between devices; use a network that allows local device-to-device connections.

If automatic discovery does not work, set `LOCALCHAT_BROADCAST` to your network’s directed broadcast address on each computer before starting the app. For example:

```bash
LOCALCHAT_BROADCAST=192.168.1.255 python ui/app.py
```

Replace the example address with the correct broadcast address for your network.

## How it works

- **Discovery:** peers broadcast room-scoped announcements over UDP.
- **Room messages:** messages are encrypted and sent directly over TCP.
- **Direct messages:** peers derive a pairwise encryption key using X25519.
- **File transfers:** files are sent in authenticated encrypted chunks and checked with SHA-256.
- **Persistence:** SQLite stores local message history on each device.
- **Host election:** peers compare their device IDs to choose a room host.

## Project structure

```text
LokalChat/
├── core/          # TCP server/client, peer discovery, peer manager, election
├── features/      # Chat protocol and file transfer
├── storage/       # SQLite message history
├── ui/            # PyQt5 screens and graphical app
├── utils/         # Encryption, framing, and checksums
├── config.py      # Local configuration and network settings
├── main.py        # Command-line entry point
└── requirements.txt
```

## Troubleshooting

### No peers appear

- Confirm both computers are on the same local network.
- Confirm they entered the same room code.
- Check that TCP `5000` and UDP `5001` are allowed through each firewall.
- Make sure the Wi-Fi network does not isolate connected devices.
- Try setting `LOCALCHAT_BROADCAST` to the network’s directed broadcast address.

### A peer is reported as having the same identity

Remove `config.json` from the duplicate computer and restart LokalChat so it can create a unique local identity. Keep the original computer’s config file.

### A message appears only on your own screen

Check that the peer list shows at least one connected peer. Messages cannot be delivered to another device until it joins the same room.

## Security and privacy notes

LokalChat is an academic project and has not undergone a security audit. Use a long, hard-to-guess room code. Messages and file contents are encrypted while being transferred, but local message history and received files are stored on disk.

## License

See [LICENSE](LICENSE).

## Acknowledgements

Author: Taha-Mohii..
