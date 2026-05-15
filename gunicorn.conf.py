bind = "0.0.0.0:8000"
workers = 2

# Forward stdout/stderr from Django's logging to Gunicorn
capture_output = True

# Send access and error logs to stdout/stderr so they appear in docker logs
accesslog = "-"
errorlog = "-"
loglevel = "info"

access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(L)ss'
