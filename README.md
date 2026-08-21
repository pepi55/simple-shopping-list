# simple-shopping-list
Simple applet for tracking shopping lists for multiple users.

 - Get new secret key: `SECRET_KEY="$(python -c 'from django.core.management import utils; print(utils.get_random_secret_key())')"`
 - Run server (https): `python -m gunicorn simple_shoppinglist.asgi:application -k uvicorn.workers.UvicornWorker --bind '0.0.0.0:443' --cert cert.pem --key key.pem --access-logfile=./access.log --error-logfile=./error.log`
