import os

KEY_TEMP_DIR = ''
API_URL = 'https://api.digitalocean.com/v2'
LOADER_TIMEOUT = 360
CONNECT_TIMEOUT = 30
DROPLET_TIMEOUT = 360
CLIENT_EXPIRE = 900
CLIENT_IP_EXPIRE = 1600
DROPLET_NAME = 'pritunl'
DROPLET_SIZE = '512mb'
DROPLET_IMAGE = 'ubuntu-14-04-x64'

DEBUG = False
PORT = int(os.getenv('PORT', 8500))
API_KEY = os.getenv('API_KEY', None)
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
ORIGIN_URL = os.getenv('ORIGIN_URL', 'http://localhost:4000')
