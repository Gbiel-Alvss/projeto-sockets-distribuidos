import logging
import random
import socket
import time
import uuid
import os
from net import encode_message, decode_stream
from protocol import validate_ack, validate_heartbeat_response, validate_task_delivery

WORKER_ID = os.getenv("WORKER_ID", "W-22")
MASTER_ID = os.getenv("MASTER_ID", "Master_16_16")
# default kept for existing behavior but can be overridden with env var
MASTER_HOST = os.getenv("MASTER_HOST", "10.62.206.22")
MASTER_PORT = int(os.getenv("MASTER_PORT", os.getenv("PORT", "8000")))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "10"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def parse_address(address):
    host, port = address.split(":")
    return host, int(port)


def run_worker():
    current_host = MASTER_HOST
    current_port = MASTER_PORT
    original_master_id = MASTER_ID
    original_master_address = f"{current_host}:{current_port}"
    borrowed = False

    logging.info("worker config: WORKER_ID=%s MASTER_HOST=%s MASTER_PORT=%s", WORKER_ID, current_host, current_port)

    while True:
        try:
            logging.info("connecting to master %s:%s", current_host, current_port)
            with socket.create_connection((current_host, current_port), timeout=5) as s:
                buffer = b""
                heartbeat = {"SERVER_UUID": MASTER_ID, "TASK": "HEARTBEAT"}
                s.sendall(encode_message(heartbeat))

                if borrowed:
                    register = {
                        "type": "register_temporary_worker",
                        "request_id": str(uuid.uuid4()),
                        "payload": {
                            "worker_id": WORKER_ID,
                            "original_master_address": original_master_address,
                        },
                    }
                    s.sendall(encode_message(register))

                while True:
                    hello = {"WORKER": "ALIVE", "WORKER_UUID": WORKER_ID}
                    if borrowed:
                        hello["SERVER_UUID"] = original_master_id
                    s.sendall(encode_message(hello))

                    should_reconnect = False
                    start = time.time()
                    while time.time() - start < 5:
                        data = s.recv(4096)
                        if not data:
                            raise ConnectionError("connection closed")
                        buffer += data
                        messages, buffer = decode_stream(buffer)
                        for msg in messages:
                            if msg.get("type") == "command_redirect":
                                print(msg)
                                new_master_address = msg["payload"]["new_master_address"]
                                current_host, current_port = parse_address(new_master_address)
                                borrowed = True
                                should_reconnect = True
                                break
                            if msg.get("type") == "command_release":
                                original_master_address = msg["payload"]["original_master_address"]
                                current_host, current_port = parse_address(original_master_address)
                                borrowed = False
                                should_reconnect = True
                                break
                            if msg.get("TASK") in ("QUERY", "NO_TASK"):
                                validate_task_delivery(msg)
                                print(msg)
                                if msg.get("TASK") == "NO_TASK":
                                    time.sleep(1)
                                    break
                                time.sleep(random.uniform(0.2, 0.8))
                                status = {"STATUS": "OK", "TASK": "QUERY", "WORKER_UUID": WORKER_ID}
                                s.sendall(encode_message(status))
                            elif msg.get("RESPONSE") == "ALIVE":
                                validate_heartbeat_response(msg)
                            elif msg.get("STATUS") == "ACK":
                                validate_ack(msg)
                        break

                    if should_reconnect:
                        break

                if should_reconnect:
                    break
        except Exception as exc:
            logging.warning("worker reconnecting after error: %s", exc)
            time.sleep(2)


if __name__ == "__main__":
    run_worker()
