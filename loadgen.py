import random
import socket
import time
from net import encode_message

MASTER_HOST = "10.62.206.20"
MASTER_PORT = 10000


def run_load():
    with socket.create_connection((MASTER_HOST, MASTER_PORT), timeout=5) as s:
        for i in range(50):
            task = {"TASK": "QUERY", "USER": f"User-{i}"}
            s.sendall(encode_message(task))
            time.sleep(random.uniform(0.05, 0.2))


if __name__ == "__main__":
    run_load()
