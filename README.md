# simple-shopping-list
Simple applet for tracking shopping lists for multiple users.

 - Get new secret key: `SECRET_KEY="$(python -c 'from django.core.management import utils; print(utils.get_random_secret_key())')"`
 - Run server: `python -m uvicorn simple_shoppinglist.asgi:application --reload --port $PORT --host $HOST`
     - Run server (https): `python -m uvicorn simple_shoppinglist.asgi:application --reload --port 8080 --host Pie3 --ssl-keyfile key.pem --ssl-certfile cert.pem`
