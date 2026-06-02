import os

os.environ.setdefault("WORKER_ID", "W-2")
os.environ.setdefault("MASTER_HOST", "10.62.206.48")
os.environ.setdefault("MASTER_PORT", "10000")

from worker import run_worker

if __name__ == "__main__":
    run_worker()
