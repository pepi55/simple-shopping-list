#python -m gunicorn simple_shoppinglist.asgi:application -k uvicorn.workers.UvicornWorker --bind 'Pie3:8080' --access-logfile=./access.log --access-logformat "%(h)s %(l)s %(u)s %(t)s '%(r)s' %(s)s %(b)s '%(f)s' '%(a)s'" --error-logfile=./error.log

#bind = 'Pie3:8080'
#bind = '[2a02:a446:bf4:0:ba27:ebff:fe49:114a]:8080'
bind = '192.168.2.43:8080'
errorlog = "./error.log"
accesslog = "./access.log"

access_log_format = "%(h)s %(l)s %(u)s %(t)s '%(r)s' %(s)s %(b)s '%(f)s' '%(a)s'"
