import json


def encode_message(msg):
    return (json.dumps(msg) + "\n").encode("utf-8")


def decode_stream(buffer):
    messages = []
    while b"\n" in buffer:
        line, buffer = buffer.split(b"\n", 1)
        if not line:
            continue
        messages.append(json.loads(line.decode("utf-8")))
    return messages, buffer
