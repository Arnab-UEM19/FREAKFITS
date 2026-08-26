import multiprocessing
import os

# Gunicorn config variables
loglevel = os.getenv("LOG_LEVEL", "info")
workers = multiprocessing.cpu_count() * 2 + 1
bind = os.getenv("BIND", "0.0.0.0:8000")
keepalive = 120
errorlog = "-"
accesslog = "-"
worker_class = "uvicorn.workers.UvicornWorker"
