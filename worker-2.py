import os

os.environ.setdefault("WORKER_ID", "W-2")
os.environ.setdefault("MASTER_HOST", "127.0.0.1")
os.environ.setdefault("MASTER_PORT", "10000")
os.environ.setdefault("MASTER_ID", "Master_A")

from worker import run_worker

if __name__ == "__main__":
    run_worker()
