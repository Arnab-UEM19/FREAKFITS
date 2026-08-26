import os

# Gunicorn config variables
loglevel = os.getenv("LOG_LEVEL", "info")

# IMPORTANT: don't derive workers from multiprocessing.cpu_count() in
# containerized environments (Render, etc). It often reports the HOST
# machine's core count rather than what's actually allocated to your
# container, which can spawn far more workers than available memory
# supports and get the deploy killed with SIGTERM.
#
# Set WEB_CONCURRENCY in Render's dashboard to tune this per plan
# (e.g. 1 for 512MB instances, 2-3 for 1-2GB instances).
workers = int(os.getenv("WEB_CONCURRENCY", "1"))

# Render provides the port to bind to via the PORT env var.
bind = os.getenv("BIND", f"0.0.0.0:{os.getenv('PORT', '8000')}")
keepalive = 120
errorlog = "-"
accesslog = "-"
worker_class = "uvicorn.workers.UvicornWorker"
