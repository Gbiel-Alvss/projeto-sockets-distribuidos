import socket
import threading
import time
import uuid

from common import free_disk, recv_json, send_json

WORKER_ID, WORKER_HOST, ELECTION_PORT = "A1", "10.62.206.44", 6001
MASTER_PORT = 5000
MASTER_HOST, MASTER_UUID = "10.62.206.50", "MASTER-INICIAL"
HB_TIMEOUT, HB_INTERVAL, MAX_ERRORS = 3, 5, 4
PEERS = [
    {"worker_id": "A2", "host": "10.62.206.43", "election_port": 6002},
    {"worker_id": "A3", "host": "10.62.206.49", "election_port": 6003},
]
STATE = {"master_host": MASTER_HOST, "master_uuid": MASTER_UUID, "is_master": False, "electing": False}
LOCK = threading.Lock()


def heartbeat_once():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(HB_TIMEOUT)
    try:
        s.connect((STATE["master_host"], MASTER_PORT))
        send_json(s, {"WORKER_ID": WORKER_ID, "SERVER_UUID": STATE["master_uuid"], "TASK": "HEARTBEAT"})
        r = recv_json(s)
        if r and r.get("TASK") == "HEARTBEAT" and r.get("RESPONSE") == "ALIVE":
            STATE["master_uuid"] = r.get("SERVER_UUID", STATE["master_uuid"])
            return True
    except Exception:
        pass
    finally:
        s.close()
    return False


def ask_status(peer):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect((peer["host"], peer["election_port"]))
        send_json(s, {"TASK": "ELECTION_STATUS_REQUEST", "FROM": WORKER_ID})
        r = recv_json(s)
        if r and r.get("TASK") == "ELECTION_STATUS_RESPONSE":
            return {"WORKER_ID": r["WORKER_ID"], "HOST": r["HOST"], "FREE_DISK": int(r["FREE_DISK"])}
    except Exception:
        return None
    finally:
        s.close()


def send_result(peer, winner, eid):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect((peer["host"], peer["election_port"]))
        send_json(s, {"TASK": "ELECTION_RESULT", "ELECTION_ID": eid, "WINNER": winner})
        r = recv_json(s)
        return True, bool(r and r.get("TASK") == "ELECTION_ACK" and r.get("ELECTION_ID") == eid)
    except Exception:
        return False, False
    finally:
        s.close()


def promote_master():
    if STATE["is_master"]:
        return
    STATE["is_master"] = True
    threading.Thread(target=master_server, daemon=True).start()


def run_election():
    with LOCK:
        if STATE["electing"]:
            return
        STATE["electing"] = True
    try:
        cands = [{"WORKER_ID": WORKER_ID, "HOST": WORKER_HOST, "FREE_DISK": free_disk()}]
        for p in PEERS:
            c = ask_status(p)
            if c:
                cands.append(c)
        winner = max(cands, key=lambda c: (c["FREE_DISK"], c["WORKER_ID"]))
        winner["MASTER_UUID"], eid = f"MASTER-{winner['WORKER_ID']}-{uuid.uuid4()}", str(uuid.uuid4())
        reachable = acks = 0
        for p in PEERS:
            r, a = send_result(p, winner, eid)
            reachable += 1 if r else 0
            acks += 1 if a else 0
        if 1 + acks >= (1 + reachable) // 2 + 1:
            STATE["master_host"], STATE["master_uuid"] = winner["HOST"], winner["MASTER_UUID"]
            if winner["WORKER_ID"] == WORKER_ID:
                promote_master()
    finally:
        STATE["electing"] = False


def handle_peer(conn):
    msg = recv_json(conn)
    if msg and msg.get("TASK") == "ELECTION_STATUS_REQUEST":
        send_json(conn, {"TASK": "ELECTION_STATUS_RESPONSE", "WORKER_ID": WORKER_ID, "HOST": WORKER_HOST, "FREE_DISK": free_disk()})
    if msg and msg.get("TASK") == "ELECTION_RESULT":
        w = msg.get("WINNER", {})
        STATE["master_host"], STATE["master_uuid"] = w.get("HOST", STATE["master_host"]), w.get("MASTER_UUID", STATE["master_uuid"])
        if w.get("WORKER_ID") == WORKER_ID:
            promote_master()
        send_json(conn, {"TASK": "ELECTION_ACK", "ELECTION_ID": msg.get("ELECTION_ID")})
    conn.close()


def election_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", ELECTION_PORT))
    s.listen()
    while True:
        c, _ = s.accept()
        threading.Thread(target=handle_peer, args=(c,), daemon=True).start()


def handle_master(conn):
    msg = recv_json(conn) or {}
    ok = msg.get("TASK") == "HEARTBEAT"
    send_json(conn, {"SERVER_UUID": STATE["master_uuid"], "TASK": msg.get("TASK", "UNKNOWN"), "RESPONSE": "ALIVE" if ok else "INVALID_TASK"})
    conn.close()


def master_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", MASTER_PORT))
    s.listen()
    while True:
        c, _ = s.accept()
        threading.Thread(target=handle_master, args=(c,), daemon=True).start()


def main():
    threading.Thread(target=election_server, daemon=True).start()
    errors = 0
    while True:
        if STATE["is_master"]:
            time.sleep(HB_INTERVAL)
            continue
        errors = 0 if heartbeat_once() else errors + 1
        if errors >= MAX_ERRORS:
            errors = 0
            run_election()
        time.sleep(HB_INTERVAL)

if __name__ == "__main__":
    main()