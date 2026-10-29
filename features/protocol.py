import time

# Message types
HELLO = "HELLO"
HELLO_ACK = "HELLO_ACK"
BYE = "BYE"
MSG = "MSG"
FILE_OFFER = "FILE_OFFER"
FILE_RESULT = "FILE_RESULT"

def make_msg(from_name: str, text:str) -> dict:
    """Create a group chat message."""
    return{
        "type" : MSG,
        "from" : from_name,
        "text" : text,
        "timestamp" : int(time.time())
    }

def make_dm(from_name: str, text: str, to_id: str) -> dict:
    return {"type": "DM", "from": from_name, "to": to_id,
            "text": text, "timestamp": int(time.time())}
    
def make_bye(from_name: str) -> dict:
    """Sent when a peer leaves."""
    return {
        "type": BYE,
        "from": from_name
    }
