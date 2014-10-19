import os

KEY_TEMP_DIR = ''
API_URL = 'https://api.digitalocean.com/v2'
OAUTH_API_URL = 'https://cloud.digitalocean.com/v1'
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
OAUTH_CLIENT_ID = os.getenv('OAUTH_CLIENT_ID', None)
OAUTH_CLIENT_SECRET = os.getenv('OAUTH_CLIENT_SECRET', None)
OAUTH_REDIRECT_URI = os.getenv('OAUTH_REDIRECT_URI',
    'http://localhost:8500/oauth')
OAUTH_REDIRECT_HOME_URI = os.getenv('OAUTH_REDIRECT_URI',
    'http://localhost:4000')
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
ORIGIN_URL = os.getenv('ORIGIN_URL', 'http://localhost:4000')
