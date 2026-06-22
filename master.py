import concurrent.futures
import os
import logging
import queue
import socket
import threading
import time
import uuid
from net import encode_message, decode_stream
from protocol import (
    validate_heartbeat_request,
    validate_master_message,
    validate_task_status,
    validate_worker_hello,
)

# ===== CONFIGURACAO (edite antes de rodar) =====
MASTER_ID = os.getenv("MASTER_ID", "Master_A")
HOST = "0.0.0.0"
PORT = int(os.getenv("MASTER_PORT", "10000"))

# Maquina 1: PEERS = ["<IP_M2>:9100"]
# Maquina 2: PEERS = ["<IP_M1>:10000"]
PEERS_STR = os.getenv("PEERS", "")
PEERS = [p.strip() for p in PEERS_STR.split(",") if p.strip()] if PEERS_STR else []

# Maquina 1: NEIGHBORS = {"Master_B": "<IP_M2>:9100"}
# Maquina 2: NEIGHBORS = {"Master_A": "<IP_M1>:10000"}
NEIGHBORS_STR = os.getenv("NEIGHBORS", "")
NEIGHBORS = {}
if NEIGHBORS_STR:
    for entry in NEIGHBORS_STR.split(","):
        entry = entry.strip()
        if ":" in entry:
            parts = entry.split(":", 2)
            if len(parts) == 3:
                mid, ip, port = parts
                NEIGHBORS[mid] = f"{ip}:{port}"
            elif len(parts) == 2:
                NEIGHBORS[parts[0]] = parts[1]

CAPACITY = 100
RELEASE_THRESHOLD = 60

# Maquina 2: colocar 200 aqui para gerar tasks
TASK_GENERATOR_COUNT = int(os.getenv("TASK_GENERATOR_COUNT", "0"))
TASK_GENERATOR_DELAY = float(os.getenv("TASK_GENERATOR_DELAY", "0.1"))
# ===============================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

TASK_QUEUE = queue.Queue()
BORROWED_WORKERS = {}
WORKERS = {}
LOCK = threading.Lock()


def send_message(conn, msg):
    conn.sendall(encode_message(msg))


def handle_master_message(msg, conn):
    validate_master_message(msg)
    msg_type = msg.get("type")
    payload = msg.get("payload") or {}

    if msg_type == "request_help":
        requester_id = payload.get("master_id")
        requester_addr = NEIGHBORS.get(requester_id)
        if not requester_addr:
            response = {
                "type": "response_rejected",
                "request_id": msg.get("request_id"),
                "payload": {"reason": "refused"},
            }
            send_message(conn, response)
            return

        with LOCK:
            available = [
                wid
                for wid in WORKERS.keys()
                if wid not in BORROWED_WORKERS
            ]

        if TASK_QUEUE.qsize() >= CAPACITY or not available:
            response = {
                "type": "response_rejected",
                "request_id": msg.get("request_id"),
                "payload": {"reason": "high_load" if TASK_QUEUE.qsize() >= CAPACITY else "no_workers_available"},
            }
            send_message(conn, response)
            return

        workers_needed = int(payload.get("workers_needed", 1))
        chosen = available[:workers_needed]
        worker_details = []
        for wid in chosen:
            worker_addr = WORKERS[wid]["addr"]
            worker_details.append({"id": wid, "address": f"{worker_addr[0]}:{worker_addr[1]}"})

        response = {
            "type": "response_accepted",
            "request_id": msg.get("request_id"),
            "payload": {"workers_offered": len(chosen), "worker_details": worker_details},
        }
        send_message(conn, response)

        for wid in chosen:
            worker_conn = WORKERS[wid]["conn"]
            redirect = {
                "type": "command_redirect",
                "request_id": str(uuid.uuid4()),
                "payload": {"new_master_address": requester_addr},
            }
            send_message(worker_conn, redirect)
        return

    if msg_type == "register_temporary_worker":
        worker_id = payload.get("worker_id")
        original_master_address = payload.get("original_master_address")
        if worker_id and original_master_address:
            with LOCK:
                BORROWED_WORKERS[worker_id] = original_master_address
        return

    if msg_type == "notify_worker_returned":
        worker_id = payload.get("worker_id")
        with LOCK:
            BORROWED_WORKERS.pop(worker_id, None)
        return


def request_help():
    request_id = str(uuid.uuid4())
    msg = {
        "type": "request_help",
        "request_id": request_id,
        "payload": {
            "master_id": MASTER_ID,
            "current_load": TASK_QUEUE.qsize(),
            "capacity": CAPACITY,
            "workers_needed": 1,
        },
    }

    def ask_peer(peer):
        host, port = peer.split(":")
        try:
            with socket.create_connection((host, int(port)), timeout=5) as s:
                send_message(s, msg)
                s.settimeout(5)
                buffer = b""
                while True:
                    buffer += s.recv(4096)
                    messages, buffer = decode_stream(buffer)
                    for resp in messages:
                        if resp.get("request_id") == request_id:
                            return resp
        except Exception as exc:
            logging.warning("peer request failed for %s: %s", peer, exc)
        return None

    # Dispara os requests concorrentemente para todos os PEERS listados
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(ask_peer, peer) for peer in PEERS]
        for future in concurrent.futures.as_completed(futures):
            resp = future.result()
            # Retorna no primeiro peer que aceitar a requisição
            if resp and resp.get("type") == "response_accepted":
                return resp
                
    return None


def release_borrowed_workers():
    with LOCK:
        borrowed_items = list(BORROWED_WORKERS.items())

    for worker_id, original_master_address in borrowed_items:
        worker_conn = WORKERS.get(worker_id, {}).get("conn")
        
        # 1. Envia comando de release para o Worker (se ainda conectado)
        if worker_conn:
            release = {
                "type": "command_release",
                "request_id": str(uuid.uuid4()),
                "payload": {"original_master_address": original_master_address},
            }
            try:
                send_message(worker_conn, release)
            except Exception as exc:
                logging.warning("failed to send command_release to worker %s: %s", worker_id, exc)

        # 2. Garante a remoção local para não ficar como fantasma, independente do Master de origem
        with LOCK:
            BORROWED_WORKERS.pop(worker_id, None)

        # 3. Tenta notificar o Master Original, tolerando a falha se ele estiver offline
        host, port = original_master_address.split(":")
        try:
            with socket.create_connection((host, int(port)), timeout=5) as s:
                notify = {
                    "type": "notify_worker_returned",
                    "request_id": str(uuid.uuid4()),
                    "payload": {"worker_id": worker_id},
                }
                send_message(s, notify)
        except Exception as exc:
            logging.warning("notify origin master failed (Master may be offline): %s", exc)


def monitor_load():
    while True:
        if TASK_QUEUE.qsize() > CAPACITY:
            request_help()
        if TASK_QUEUE.qsize() < RELEASE_THRESHOLD and BORROWED_WORKERS:
            release_borrowed_workers()
        time.sleep(1)


def task_generator():
    for index in range(TASK_GENERATOR_COUNT):
        TASK_QUEUE.put(f"User-{index}")
        logging.info("generated task %s/%s", index + 1, TASK_GENERATOR_COUNT)
        if TASK_GENERATOR_DELAY > 0:
            time.sleep(TASK_GENERATOR_DELAY)


def handle_connection(conn, addr):
    logging.info("connection from %s", addr)
    buffer = b""
    worker_id = None
    while True:
        data = conn.recv(4096)
        if not data:
            break
        buffer += data
        messages, buffer = decode_stream(buffer)
        for msg in messages:
            try:
                if msg.get("type"):
                    handle_master_message(msg, conn)
                    continue

                if msg.get("TASK") == "HEARTBEAT":
                    validate_heartbeat_request(msg)
                    response = {"SERVER_UUID": MASTER_ID, "TASK": "HEARTBEAT", "RESPONSE": "ALIVE"}
                    send_message(conn, response)
                    continue

                if msg.get("TASK") == "QUERY" and msg.get("USER") and not msg.get("WORKER"):
                    TASK_QUEUE.put(msg.get("USER"))
                    continue

                if msg.get("WORKER") == "ALIVE":
                    validate_worker_hello(msg)
                    worker_id = msg.get("WORKER_UUID")
                    with LOCK:
                        WORKERS[worker_id] = {"conn": conn, "addr": addr}
                    if TASK_QUEUE.empty():
                        send_message(conn, {"TASK": "NO_TASK"})
                    else:
                        task = TASK_QUEUE.get()
                        send_message(conn, {"TASK": "QUERY", "USER": task})
                    continue

                if msg.get("STATUS"):
                    validate_task_status(msg)
                    logging.info("task status from %s: %s", msg.get("WORKER_UUID"), msg.get("STATUS"))
                    send_message(conn, {"STATUS": "ACK", "WORKER_UUID": msg.get("WORKER_UUID")})
                    continue
            except ValueError as exc:
                logging.warning("invalid payload: %s (%s)", msg, exc)

    if worker_id:
        with LOCK:
            WORKERS.pop(worker_id, None)
            BORROWED_WORKERS.pop(worker_id, None)
    conn.close()


def accept_loop():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()
    logging.info("Master listening on %s:%s", HOST, PORT)
    while True:
        conn, addr = server.accept()
        t = threading.Thread(target=handle_connection, args=(conn, addr), daemon=True)
        t.start()


def run_master():
    if TASK_GENERATOR_COUNT > 0:
        generator = threading.Thread(target=task_generator, daemon=True)
        generator.start()
    monitor = threading.Thread(target=monitor_load, daemon=True)
    monitor.start()
    accept_loop()


if __name__ == "__main__":
    run_master()
