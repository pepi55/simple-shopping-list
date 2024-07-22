#python -m gunicorn simple_shoppinglist.asgi:application -k uvicorn.workers.UvicornWorker --bind 'Pie3:8080' --access-logfile=./access.log --access-logformat "%(h)s %(l)s %(u)s %(t)s '%(r)s' %(s)s %(b)s '%(f)s' '%(a)s'" --error-logfile=./error.log

bind = 'Pie3:8080'
errorlog = "./error.log"
accesslog = "./access.log"

access_log_format = "%(h)s %(l)s %(u)s %(t)s '%(r)s' %(s)s %(b)s '%(f)s' '%(a)s'"
