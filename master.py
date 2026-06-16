import argparse
import concurrent.futures
import logging
import platform
import queue
import socket
import threading
import time
import uuid
import random
import os
from net import encode_message, decode_stream
from protocol import (
    validate_heartbeat_request,
    validate_master_message,
    validate_task_status,
    validate_worker_hello,
)
from supervisor import send_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

HOST = "0.0.0.0"
MASTER_ID = "Master_16_16"
PORT = 8000
CAPACITY = 100
RELEASE_THRESHOLD = 60
PEERS = []
NEIGHBORS = {}
WORKER_ADDRESS = None

TASK_QUEUE = queue.Queue()
BORROWED_WORKERS = {}
LENT_WORKERS = {}
WORKERS = {}
WORKER_BUSY = set()
TASKS_COMPLETED = 0
TASKS_FAILED = 0
TASK_TIMESTAMPS = {}
SUPERVISOR_ENABLED = True
SUPERVISOR_HOST = "10.62.206.206"
SUPERVISOR_PORT = 8000
SERVER_UUID = "Master16_16"
HOSTNAME = "Master16_16"
LOCK = threading.Lock()

NUM_TASKS_TO_GENERATE = int(os.getenv("NUM_TASKS", 150))

def generate_tasks():
    """
    Gera um número pré-definido de tarefas e as adiciona à fila de tarefas.
    O número de tarefas é determinado pela variável de ambiente NUM_TASKS.
    """
    logging.info(f"Task generator starting, will generate {NUM_TASKS_TO_GENERATE} tasks.")
    for i in range(NUM_TASKS_TO_GENERATE):
        user = f"User-{i}"
        with LOCK:
            TASK_TIMESTAMPS[user] = time.time()
        TASK_QUEUE.put(user)
        logging.debug(f"Generated task for {user}")
        time.sleep(random.uniform(0.05, 0.2))
    logging.info("Task generator finished.")


def parse_args():
    parser = argparse.ArgumentParser(description="Master node for distributed worker pool")
    parser.add_argument("--id", default=MASTER_ID, help="Unique master identifier")
    parser.add_argument("--port", type=int, default=PORT, help="Listening port")
    parser.add_argument("--capacity", type=int, default=CAPACITY, help="Saturation threshold (max pending tasks)")
    parser.add_argument("--release", type=int, default=RELEASE_THRESHOLD, help="Release threshold (hysteresis)")
    parser.add_argument("--peers", default="", help="Comma-separated peer addresses (ip:port)")
    parser.add_argument("--neighbors", default="", help="Comma-separated master_id=ip:port entries")
    parser.add_argument("--worker-address", default=None, help="Address workers use to reach this master (ip:port)")
    parser.add_argument("--server-uuid", default=None, help="UUID for supervisor dashboard (e.g. michel_1)")
    parser.add_argument("--hostname", default=None, help="Hostname for supervisor report (default: platform.node())")
    parser.add_argument("--supervisor-host", default=SUPERVISOR_HOST, help="Supervisor TCP/TLS host")
    parser.add_argument("--supervisor-port", type=int, default=SUPERVISOR_PORT, help="Supervisor TCP/TLS port")
    parser.add_argument("--no-supervisor", action="store_true", help="Disable supervisor reporting")
    return parser.parse_args()


def send_message(conn, msg):
    conn.sendall(encode_message(msg))


def log_m2m(direction, msg_type, request_id, peer_id=None, details=""):
    logging.info(
        "M2M %s type=%s request_id=%s%s%s",
        direction,
        msg_type,
        request_id,
        f" peer={peer_id}" if peer_id else "",
        f" {details}" if details else "",
    )


def get_worker_address(host, port):
    return f"{host}:{port}"


def count_local_workers():
    return len(WORKERS) - len(BORROWED_WORKERS)


def handle_master_message(msg, conn):
    validate_master_message(msg)
    msg_type = msg.get("type")
    payload = msg.get("payload") or {}
    request_id = msg.get("request_id")

    log_m2m("RECV", msg_type, request_id, details=str(payload))

    if msg_type == "request_help":
        requester_id = payload.get("master_id")
        requester_addr = NEIGHBORS.get(requester_id)
        if not requester_addr:
            response = {
                "type": "response_rejected",
                "request_id": request_id,
                "payload": {"reason": "refused"},
            }
            send_message(conn, response)
            log_m2m("SEND", "response_rejected", request_id, peer_id=requester_id, details="reason=refused")
            return

        with LOCK:
            available = [
                wid
                for wid in WORKERS.keys()
                if wid not in LENT_WORKERS
            ]

        if TASK_QUEUE.qsize() >= CAPACITY or not available:
            reason = "high_load" if TASK_QUEUE.qsize() >= CAPACITY else "no_workers_available"
            response = {
                "type": "response_rejected",
                "request_id": request_id,
                "payload": {"reason": reason},
            }
            send_message(conn, response)
            log_m2m("SEND", "response_rejected", request_id, peer_id=requester_id, details=f"reason={reason}")
            return

        workers_needed = int(payload.get("workers_needed", 1))
        chosen = available[:workers_needed]
        worker_details = [
            {"id": wid, "address": get_worker_address(WORKERS[wid]["addr"][0], WORKERS[wid]["addr"][1])}
            for wid in chosen
        ]

        response = {
            "type": "response_accepted",
            "request_id": request_id,
            "payload": {
                "workers_offered": len(chosen),
                "worker_details": worker_details,
            },
        }
        send_message(conn, response)
        log_m2m("SEND", "response_accepted", request_id, peer_id=requester_id, details=f"offered={len(chosen)}")

        for wid in chosen:
            worker_conn = WORKERS[wid]["conn"]
            redirect = {
                "type": "command_redirect",
                "request_id": str(uuid.uuid4()),
                "payload": {"new_master_address": requester_addr},
            }
            send_message(worker_conn, redirect)
            log_m2m("SEND", "command_redirect", redirect["request_id"], peer_id=wid, details=f"to={requester_addr}")
            with LOCK:
                LENT_WORKERS[wid] = requester_addr
        return

    if msg_type == "register_temporary_worker":
        worker_id = payload.get("worker_id")
        original_master_address = payload.get("original_master_address")
        if worker_id and original_master_address:
            with LOCK:
                BORROWED_WORKERS[worker_id] = original_master_address
            logging.info(
                "borrowed worker %s registered (origin=%s) local=%d borrowed=%d",
                worker_id,
                original_master_address,
                count_local_workers(),
                len(BORROWED_WORKERS),
            )
        return

    if msg_type == "notify_worker_returned":
        worker_id = payload.get("worker_id")
        with LOCK:
            LENT_WORKERS.pop(worker_id, None)
        logging.info(
            "worker %s returned to origin, lent=%d borrowed=%d",
            worker_id,
            len(LENT_WORKERS),
            len(BORROWED_WORKERS),
        )
        return


def request_help():
    current_load = TASK_QUEUE.qsize()
    if current_load <= CAPACITY:
        return None

    excess = current_load - CAPACITY
    workers_needed = max(1, (excess + 9) // 10)

    request_id = str(uuid.uuid4())
    msg = {
        "type": "request_help",
        "request_id": request_id,
        "payload": {
            "master_id": MASTER_ID,
            "current_load": current_load,
            "capacity": CAPACITY,
            "workers_needed": workers_needed,
        },
    }

    log_m2m("SEND", "request_help", request_id, details=f"load={current_load} needed={workers_needed}")

    def ask_peer(peer):
        host_str, port_str = peer.split(":")
        try:
            with socket.create_connection((host_str, int(port_str)), timeout=5) as s:
                send_message(s, msg)
                s.settimeout(5)
                buffer = b""
                while True:
                    try:
                        data = s.recv(4096)
                        if not data:
                            break
                    except socket.timeout:
                        break
                    buffer += data
                    messages, buffer = decode_stream(buffer)
                    for resp in messages:
                        if resp.get("request_id") == request_id:
                            log_m2m(
                                "RECV",
                                resp.get("type", "unknown"),
                                request_id,
                                peer_id=peer,
                                details=str(resp.get("payload", {})),
                            )
                            return resp
        except Exception as exc:
            logging.warning("M2M request to peer %s failed: %s", peer, exc)
        return None

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(ask_peer, peer) for peer in PEERS]
        for future in concurrent.futures.as_completed(futures):
            resp = future.result()
            if resp and resp.get("type") == "response_accepted":
                return resp

    return None


def release_borrowed_workers():
    with LOCK:
        borrowed_items = list(BORROWED_WORKERS.items())

    for worker_id, original_master_address in borrowed_items:
        worker_info = WORKERS.get(worker_id)
        worker_conn = worker_info.get("conn") if worker_info else None

        if worker_conn:
            release = {
                "type": "command_release",
                "request_id": str(uuid.uuid4()),
                "payload": {"original_master_address": original_master_address},
            }
            try:
                send_message(worker_conn, release)
                log_m2m("SEND", "command_release", release["request_id"], peer_id=worker_id, details=f"origin={original_master_address}")
            except Exception as exc:
                logging.warning("failed to send command_release to worker %s: %s", worker_id, exc)

        with LOCK:
            BORROWED_WORKERS.pop(worker_id, None)

        host_str, port_str = original_master_address.split(":")
        try:
            with socket.create_connection((host_str, int(port_str)), timeout=5) as s:
                notify = {
                    "type": "notify_worker_returned",
                    "request_id": str(uuid.uuid4()),
                    "payload": {"worker_id": worker_id},
                }
                send_message(s, notify)
                log_m2m("SEND", "notify_worker_returned", notify["request_id"], details=f"worker={worker_id}")
        except Exception as exc:
            logging.warning("notify origin master failed (may be offline): %s", exc)

        logging.info(
            "released borrowed worker %s, local=%d borrowed=%d",
            worker_id,
            count_local_workers(),
            len(BORROWED_WORKERS),
        )

    if NUM_TASKS_TO_GENERATE > 0:
        task_gen_thread = threading.Thread(target=generate_tasks, daemon=True)
        task_gen_thread.start()

    monitor = threading.Thread(target=monitor_load, daemon=True)
    monitor.start()

def monitor_load():
    while True:
        current_load = TASK_QUEUE.qsize()
        borrowed_count = len(BORROWED_WORKERS)
        if current_load > CAPACITY:
            logging.info("saturation detected: load=%d capacity=%d borrowed=%d", current_load, CAPACITY, borrowed_count)
            request_help()
        elif current_load < RELEASE_THRESHOLD and borrowed_count:
            logging.info("load normalized: load=%d threshold=%d releasing %d workers", current_load, RELEASE_THRESHOLD, borrowed_count)
            release_borrowed_workers()
        time.sleep(1)


def handle_connection(conn, addr):
    logging.info("connection from %s", addr)
    buffer = b""
    worker_id = None
    while True:
        try:
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
                        task_user = msg.get("USER")
                        with LOCK:
                            TASK_TIMESTAMPS[task_user] = time.time()
                        TASK_QUEUE.put(task_user)
                        continue

                    if msg.get("WORKER") == "ALIVE":
                        validate_worker_hello(msg)
                        worker_id = msg.get("WORKER_UUID")
                        with LOCK:
                            WORKERS[worker_id] = {"conn": conn, "addr": addr}
                        server_uuid = msg.get("SERVER_UUID", "")
                        logging.info(
                            "worker %s registered%s local=%d borrowed=%d",
                            worker_id,
                            f" (borrowed, origin={server_uuid})" if server_uuid else "",
                            count_local_workers(),
                            len(BORROWED_WORKERS),
                        )
                        if TASK_QUEUE.empty():
                            send_message(conn, {"TASK": "NO_TASK"})
                        else:
                            task = TASK_QUEUE.get()
                            with LOCK:
                                TASK_TIMESTAMPS.pop(task, None)
                                WORKER_BUSY.add(worker_id)
                            send_message(conn, {"TASK": "QUERY", "USER": task})
                        continue

                    if msg.get("STATUS"):
                        validate_task_status(msg)
                        wid = msg.get("WORKER_UUID")
                        status_val = msg.get("STATUS")
                        logging.info("task %s from worker %s", status_val, wid)
                        with LOCK:
                            WORKER_BUSY.discard(wid)
                            if status_val == "OK":
                                TASKS_COMPLETED += 1
                            elif status_val == "NOK":
                                TASKS_FAILED += 1
                            # When task done, check queue for next task
                            if not TASK_QUEUE.empty():
                                next_task = TASK_QUEUE.get()
                                TASK_TIMESTAMPS.pop(next_task, None)
                                WORKER_BUSY.add(wid)
                                send_message(conn, {"TASK": "QUERY", "USER": next_task})
                                continue
                        send_message(conn, {"STATUS": "ACK", "WORKER_UUID": msg.get("WORKER_UUID")})
                        continue

                    logging.warning("unknown message from %s: %s", addr, msg)

                except ValueError as exc:
                    logging.warning("invalid payload from %s: %s (%s)", addr, msg, exc)

        except Exception as exc:
            logging.warning("connection error with %s: %s", addr, exc)
            break

    if worker_id:
        with LOCK:
            WORKERS.pop(worker_id, None)
            was_borrowed = BORROWED_WORKERS.pop(worker_id, None) or (worker_id in LENT_WORKERS)
            WORKER_BUSY.discard(worker_id)
        if worker_id in LENT_WORKERS:
            logging.info(
                "lent worker %s disconnected (expected), lent=%d borrowed=%d",
                worker_id,
                len(LENT_WORKERS),
                len(BORROWED_WORKERS),
            )
        elif was_borrowed:
            logging.info(
                "borrowed worker %s disconnected, local=%d borrowed=%d",
                worker_id,
                count_local_workers(),
                len(BORROWED_WORKERS),
            )
        else:
            logging.info(
                "local worker %s disconnected, local=%d borrowed=%d",
                worker_id,
                count_local_workers(),
                len(BORROWED_WORKERS),
            )
    conn.close()


def supervisor_report_loop():
    while SUPERVISOR_ENABLED:
        with LOCK:
            workers_snapshot = dict(WORKERS)
            borrowed_snapshot = dict(BORROWED_WORKERS)
            lent_snapshot = dict(LENT_WORKERS)
            busy_snapshot = set(WORKER_BUSY)
            completed = TASKS_COMPLETED
            failed = TASKS_FAILED
            timestamps_snapshot = dict(TASK_TIMESTAMPS)
        send_report(
            SERVER_UUID, HOSTNAME,
            TASK_QUEUE, workers_snapshot,
            borrowed_snapshot, lent_snapshot,
            NEIGHBORS, CAPACITY, RELEASE_THRESHOLD,
            completed, failed, len(busy_snapshot),
            timestamps_snapshot,
            SUPERVISOR_HOST, SUPERVISOR_PORT,
        )
        time.sleep(10)


def accept_loop(bind_port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, bind_port))
    server.listen()
    logging.info("Master %s listening on %s:%s", MASTER_ID, HOST, bind_port)
    while True:
        conn, addr = server.accept()
        t = threading.Thread(target=handle_connection, args=(conn, addr), daemon=True)
        t.start()


def run_master():
    args = parse_args()

    global MASTER_ID, PORT, CAPACITY, RELEASE_THRESHOLD, PEERS, NEIGHBORS, WORKER_ADDRESS
    global SUPERVISOR_ENABLED, SUPERVISOR_HOST, SUPERVISOR_PORT, SERVER_UUID, HOSTNAME
    MASTER_ID = args.id
    PORT = args.port
    CAPACITY = args.capacity
    RELEASE_THRESHOLD = args.release
    WORKER_ADDRESS = args.worker_address or f"127.0.0.1:{PORT}"
    SERVER_UUID = args.server_uuid or MASTER_ID
    HOSTNAME = "Master16_16"
    SUPERVISOR_ENABLED = not args.no_supervisor
    SUPERVISOR_HOST = args.supervisor_host
    SUPERVISOR_PORT = args.supervisor_port

    if args.peers:
        PEERS = [p.strip() for p in args.peers.split(",")]
    if args.neighbors:
        for entry in args.neighbors.split(","):
            if "=" in entry:
                mid, addr = entry.split("=", 1)
                NEIGHBORS[mid.strip()] = addr.strip()

    logging.info(
        "Master %s starting (port=%d capacity=%d release=%d peers=%s neighbors=%s worker_addr=%s supervisor=%s)",
        MASTER_ID,
        PORT,
        CAPACITY,
        RELEASE_THRESHOLD,
        PEERS,
        NEIGHBORS,
        WORKER_ADDRESS,
        f"{SUPERVISOR_HOST}:{SUPERVISOR_PORT}" if SUPERVISOR_ENABLED else "disabled",
    )

        # Inicia o gerador de tarefas em um thread separado
    if NUM_TASKS_TO_GENERATE > 0:
        task_gen_thread = threading.Thread(target=generate_tasks, daemon=True)
        task_gen_thread.start()

    monitor = threading.Thread(target=monitor_load, daemon=True)
    monitor.start()

    if SUPERVISOR_ENABLED:
        supervisor_thread = threading.Thread(target=supervisor_report_loop, daemon=True)
        supervisor_thread.start()

    accept_loop(PORT)


if __name__ == "__main__":
    run_master()
