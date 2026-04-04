#!/usr/bin/env python3

import os
import sys
sys.path.append('ET-Machine')

import src.pardina
import pardinalink

os.chdir('ET-Machine')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Machine.settings')
os.environ.setdefault('HOSTS', 'tckmn.mit.edu,machine.tck.mn')
from django.core.management import execute_from_command_line

import threading
import asyncio

backend = src.pardina.Backend(False)
pardinalink.link.backend = backend
threading.Thread(target=lambda: backend.go(True)).start()

execute_from_command_line(sys.argv + ['runserver', '0.0.0.0:7874', '--noreload'])
