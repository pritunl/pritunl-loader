from constants import *
from exceptions import *
from loader import Loader
import loader
import os
import json
import time
import base64
import hashlib
import flask
import uuid
import cherrypy.wsgiserver
import tunldb
import threading
import functools
import werkzeug.debug.tbtools
import redis
import logging
import requests
import urllib

app = flask.Flask('pritunl_loader')
app.secret_key = os.urandom(32)
app_db = tunldb.TunlDB()
app_db.set('state', 't')
redis_conn = redis.StrictRedis.from_url(REDIS_URL)

def get_remote_addr():
    if 'X-Forwarded-For' in flask.request.headers:
        return flask.request.headers.getlist('X-Forwarded-For')[0]
    if 'X-Real-Ip' in flask.request.headers:
        return flask.request.headers.getlist('X-Real-Ip')[0]
    return flask.request.remote_addr

def cors_headers(call):
    @functools.wraps(call)
    def wrapped(*args, **kwargs):
        if flask.request.method == 'OPTIONS':
            response = app.make_default_options_response()
        else:
            response = flask.make_response(call(*args, **kwargs))

        if (flask.request.referrer or 'https').startswith('https'):
            origin_url = 'https:' + ORIGIN_URL
        else:
            origin_url = 'http:' + ORIGIN_URL

        response.headers.add('Access-Control-Allow-Origin', origin_url)
        response.headers.add('Access-Control-Allow-Methods',
            'GET,PUT,POST,DELETE,OPTIONS')
        response.headers.add('Access-Control-Max-Age', '600')
        response.headers.add('Access-Control-Allow-Headers',
            'Authorization,Content-Type,Accept,Origin,User-Agent,' +
            'DNT,Cache-Control,X-Mx-ReqToken,Keep-Alive,' +
            'X-Requested-With,If-Modified-Since')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response
    return wrapped

def create_droplet(client_id, api_key, region):
    loader = Loader(api_key, region)
    try:
        loader.install()
        time.sleep(10)
        app_db.dict_remove(client_id, 'error')
        app_db.dict_set(client_id, 'success', ('Your Pritunl server has ' +
            'successfully launched, you will be emailed a new root ' +
            'password to access the droplet. You may login to your ' +
            'Pritunl server using the default username and password ' +
            '"admin" at: <a href="https://%s:9700/" target="_blank">' +
            'https://%s:9700/</a>') % (loader.host, loader.host))
    except InvalidApiKey:
        logging.exception('InvalidApiKey')
        app_db.dict_set(client_id, 'error', 'Failed to create Pritunl ' +
        'server, DigitalOcean API token is invalid.')
    except KeyImportError:
        logging.exception('KeyImportError')
        app_db.dict_set(client_id, 'error', 'Failed to create Pritunl ' +
        'server, unable to import ssh key into DigitalOcean.')
    except CreateDropletError:
        logging.exception('CreateDropletError')
        app_db.dict_set(client_id, 'error', 'Failed to create Pritunl ' +
        'server, unable to create droplet.')
    except ResetPasswordError:
        logging.exception('ResetPasswordError')
        app_db.dict_set(client_id, 'error', 'Failed to create Pritunl ' +
        'server, failed to reset password.')
    except DropletTimeout:
        logging.exception('DropletTimeout')
        app_db.dict_set(client_id, 'error', 'Failed to create Pritunl ' +
        'server, connection to droplet timed out.')
    except DropletExecError:
        logging.exception('DropletExecError')
        app_db.dict_set(client_id, 'error', 'Failed to create Pritunl ' +
        'server, failed to execute command on server.')
    except:
        logging.exception('Unknown')
        app_db.dict_set(client_id, 'error', 'Failed to create Pritunl ' +
        'server, unknown error occurred.')
    app_db.dict_set(client_id, 'status', 'f')
    app_db.expire(client_id, CLIENT_EXPIRE)
    app_db.publish(client_id, 'event')

def filter_str(in_str):
    if not in_str:
        return in_str
    return ''.join(x for x in in_str if x.isalnum())

def jsonify(data=None, status_code=None):
    if not isinstance(data, basestring):
        data = json.dumps(data)
    response = flask.Response(response=data, mimetype='application/json')
    response.headers.add('Cache-Control',
        'no-cache, no-store, must-revalidate')
    response.headers.add('Pragma', 'no-cache')
    if status_code is not None:
        response.status_code = status_code
    return response

def get_client_dict(client_id):
    status = app_db.dict_get(client_id, 'status')
    return {
        'id': client_id,
        'status': True if (status == 't') else False,
        'region': app_db.dict_get(client_id, 'region'),
        'success': app_db.dict_get(client_id, 'success'),
        'error': app_db.dict_get(client_id, 'error'),
    }

@app.route('/loader', methods=['GET', 'OPTIONS'])
@app.route('/loader/<client_id>', methods=['GET', 'OPTIONS'])
@cors_headers
def loader_get(client_id=None):
    if 'id' in flask.session:
        app_db.remove(get_remote_addr())
    client_id = client_id or flask.session.get('id') or app_db.get(
        get_remote_addr())
    if not client_id:
        client_id = uuid.uuid4().hex
        flask.session['id'] = client_id
        app_db.expire(get_remote_addr(), CLIENT_IP_EXPIRE)
        app_db.set(get_remote_addr(), client_id)

    if app_db.get('state') != 't' and \
            app_db.dict_get(client_id, 'status') != 't':
        return jsonify(get_client_dict(client_id), 503)

    return jsonify(get_client_dict(client_id))

@app.route('/loader', methods=['POST'])
@app.route('/loader/<client_id>', methods=['POST'])
@cors_headers
def loader_post(client_id=None):
    if 'id' in flask.session:
        app_db.remove(get_remote_addr())
    client_id = client_id or flask.session.get('id') or app_db.get(
        get_remote_addr())
    if not client_id:
        client_id = uuid.uuid4().hex
        flask.session['id'] = client_id
        app_db.expire(get_remote_addr(), CLIENT_IP_EXPIRE)
        app_db.set(get_remote_addr(), client_id)

    region = filter_str(flask.request.json['region'])[:256]

    if app_db.dict_get(client_id, 'status') != 't':
        if app_db.get('state') != 't':
            app_db.remove(client_id)
            return jsonify(get_client_dict(client_id), 503)
        redis_conn.set(uuid.uuid4().hex, str(int(time.time())))
        app_db.expire(client_id, CLIENT_EXPIRE)
        app_db.dict_set(client_id, 'status', 'a')
        app_db.dict_set(client_id, 'region', region)

    return jsonify({
        'oauth_url': '%s/oauth/authorize?%s' % (
            OAUTH_API_URL, urllib.urlencode({
                'client_id': OAUTH_CLIENT_ID,
                'redirect_uri': OAUTH_REDIRECT_URI,
                'response_type': 'code',
                'scope': 'read write',
                'state': uuid.uuid4().hex,
            })),
    })

@app.route('/oauth', methods=['GET'])
@cors_headers
def oauth_get():
    client_id = flask.session.get('id') or app_db.get(get_remote_addr())
    oauth_error = flask.request.args.get('error')
    oauth_code = flask.request.args.get('code')

    limit_key = get_remote_addr() + '_limit'
    if app_db.get(limit_key):
        return flask.redirect(OAUTH_REDIRECT_HOME_URI + '/?error=err#install')
    app_db.expire(limit_key, 3)
    app_db.set(limit_key, 't')

    if oauth_error == 'access_denied' or not oauth_code:
        return flask.redirect(OAUTH_REDIRECT_HOME_URI + '/?error=oad#install')

    response = requests.post(
        '%s/oauth/token' % OAUTH_API_URL,
        params={
            'grant_type': 'authorization_code',
            'code': oauth_code,
            'client_id': OAUTH_CLIENT_ID,
            'client_secret': OAUTH_CLIENT_SECRET,
            'redirect_uri': OAUTH_REDIRECT_URI,
        },
    )

    if response.status_code != 200:
        return flask.redirect(OAUTH_REDIRECT_HOME_URI + '/?error=oad#install')

    api_key = response.json()['access_token']

    status = app_db.dict_get(client_id, 'status')
    if status == 'a':
        app_db.expire(client_id, CLIENT_EXPIRE)
        app_db.dict_set(client_id, 'status', 't')
        region = app_db.dict_get(client_id, 'region')
        threading.Thread(target=create_droplet,
            args=(client_id, api_key, region)).start()
    elif status == 't':
        pass
    else:
        return flask.redirect(OAUTH_REDIRECT_HOME_URI + '/?error=err#install')

    return flask.redirect(OAUTH_REDIRECT_HOME_URI + '/#install')

@app.route('/loader', methods=['DELETE'])
@app.route('/loader/<client_id>', methods=['DELETE'])
@cors_headers
def loader_delete(client_id=None):
    client_id = client_id or flask.session.get('id') or app_db.get(
        get_remote_addr())
    if client_id:
        app_db.remove(client_id)
        flask.session.pop('id', None)
    return jsonify({})

@app.route('/poll', methods=['GET', 'OPTIONS'])
@app.route('/poll/<client_id>', methods=['GET', 'OPTIONS'])
@cors_headers
def poll_get(client_id=None):
    if 'id' in flask.session:
        app_db.remove(get_remote_addr())
    client_id = client_id or flask.session.get('id') or app_db.get(
        get_remote_addr())
    if not client_id:
        client_id = uuid.uuid4().hex
        flask.session['id'] = client_id
        app_db.expire(get_remote_addr(), CLIENT_IP_EXPIRE)
        app_db.set(get_remote_addr(), client_id)

    if app_db.dict_get(client_id, 'status') == 't':
        for msg in app_db.subscribe(client_id, 25):
            break

    return jsonify(get_client_dict(client_id))

@app.route('/admin/<api_key>/status', methods=['GET'])
@cors_headers
def admin_status(api_key):
    if API_KEY and api_key != API_KEY:
        raise flask.abort(404)

    clients = {}
    for client_id in app_db.keys():
        if client_id == 'state' or '.' in client_id:
            continue
        clients[client_id] = {
            'status': app_db.dict_get(client_id, 'status'),
        }
    redis_info = redis_conn.info()
    redis_info = redis_info.get('db0', {})

    return jsonify({
        'state': app_db.get('state'),
        'count': redis_info.get('keys'),
        'clients': clients,
    })

@app.route('/admin/<api_key>/on', methods=['GET'])
@cors_headers
def admin_on(api_key):
    if API_KEY and api_key != API_KEY:
        raise flask.abort(404)
    redis_conn.set('state', 't')
    redis_conn.publish('state', 't')
    return jsonify({
        'state': True,
    })

@app.route('/admin/<api_key>/off', methods=['GET'])
@cors_headers
def admin_off(api_key):
    if API_KEY and api_key != API_KEY:
        raise flask.abort(404)
    redis_conn.set('state', 'f')
    redis_conn.publish('state', 'f')
    return jsonify({
        'state': False,
    })

def start_server():
    def state_sub():
        try:
            redis_pubsub = redis_conn.pubsub()
            redis_pubsub.subscribe('state')
            for item in redis_pubsub.listen():
                if item['type'] == 'message':
                    app_db.set('state', item['data'])
        except:
            time.sleep(0.5)
            state_sub()
    state_sub_thread = threading.Thread(target=state_sub)
    state_sub_thread.daemon = True
    state_sub_thread.start()

    try:
        app_db.set('state', redis_conn.get('state') or 't')
    except:
        pass

    if DEBUG:
        app.debug = True
        app.run(host='0.0.0.0', port=PORT, threaded=True)
    else:
        server = cherrypy.wsgiserver.CherryPyWSGIServer(('0.0.0.0', PORT), app)
        try:
            server.start()
        except (KeyboardInterrupt, SystemExit), exc:
            server.stop()
