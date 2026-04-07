import json
import shutil

BUFFER_SIZE = 1024


def send_json(sock, data):
    sock.sendall((json.dumps(data) + "\n").encode("utf-8"))


def extract_messages(buffer):
    messages = []
    while "\n" in buffer:
        line, buffer = buffer.split("\n", 1)
        if line.strip():
            messages.append(line)
    return messages, buffer


def recv_json(sock):
    buffer = ""
    while True:
        data = sock.recv(BUFFER_SIZE)
        if not data:
            return None
        buffer += data.decode("utf-8")
        messages, buffer = extract_messages(buffer)
        if not messages:
            continue
        try:
            return json.loads(messages[0])
        except json.JSONDecodeError:
            return None


def free_disk():
    return shutil.disk_usage(".").free