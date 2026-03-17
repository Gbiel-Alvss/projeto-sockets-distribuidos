import json

BUFFER_SIZE = 1024


def send_json(sock, data):
    """
    Envia um dicionário em formato JSON, terminado com \n
    """
    message = json.dumps(data) + "\n"
    sock.sendall(message.encode("utf-8"))


def extract_messages(buffer):
    """
    Extrai mensagens completas separadas por \n
    Retorna:
    - lista de linhas completas
    - restante do buffer
    """
    messages = []

    while "\n" in buffer:
        line, buffer = buffer.split("\n", 1)
        if line.strip():
            messages.append(line)

    return messages, buffer