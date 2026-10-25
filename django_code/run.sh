#!/bin/bash

SECRET_KEY="$(python -c 'from django.core.management import utils; print(utils.get_random_secret_key())')" python -m gunicorn simple_shoppinglist.asgi:application -k uvicorn.workers.UvicornWorker -c gunicorn_conf.py --log-config ./logging.conf
