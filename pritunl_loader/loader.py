from constants import *
from exceptions import *
import uuid
import subprocess
import os
import paramiko
import base64
import time
import requests
import json
import socket

class IgnorePolicy(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self, *args, **kwargs):
        pass

class Loader:
    def __init__(self, api_key, region):
        self.api_key = api_key
        self.region = region
        self.droplet_id = None
        self.host = None
        self.private_key = None
        self.public_key = None
        self.public_key_id = None

    def generate_key(self):
        key_path = os.path.join(KEY_TEMP_DIR, uuid.uuid4().hex)
        pub_key_path = key_path + '.pub'
        process = subprocess.check_output([
            'ssh-keygen', '-b', '1024', '-t', 'rsa', '-C', 'pritunl',
            '-N', '', '-f', key_path,
        ])
        self.private_key = paramiko.RSAKey(filename=key_path)
        os.remove(key_path)
        self.public_key = open(pub_key_path).read().strip()
        os.remove(pub_key_path)

    def import_key(self):
        response = requests.post(
            '%s/account/keys' % API_URL,
            headers={
                'Authorization': 'Bearer %s' % self.api_key,
                'Content-Type': 'application/json',
            },
            data=json.dumps({
                'name': DROPLET_NAME,
                'public_key': self.public_key,
            }),
        )
        if response.status_code < 200 or response.status_code >= 300:
            if response.json().get('id') == 'unauthorized':
                raise InvalidApiKey('API key is invalid')
            raise KeyImportError('Failed to import ssh key')
        self.public_key_id = response.json()['ssh_key']['id']

    def reset_password(self):
        if not self.droplet_id:
            return
        response = requests.post(
            '%s/droplets/%s/actions' % (API_URL, self.droplet_id),
            headers={
                'Authorization': 'Bearer %s' % self.api_key,
                'Content-Type': 'application/json',
            },
            data=json.dumps({
                'type': 'password_reset',
            }),
        )
        if response.status_code < 200 or response.status_code >= 300:
            if response.json().get('id') == 'unauthorized':
                raise InvalidApiKey('API key is invalid')
            raise ResetPasswordError('Failed to reset droplet password')

    def remove_key(self):
        if not self.public_key_id:
            return
        response = requests.delete(
            '%s/account/keys/%s' % (API_URL, self.public_key_id),
            headers={
                'Authorization': 'Bearer %s' % self.api_key,
            },
        )

    def create_droplet(self):
        if not self.public_key:
            self.generate_key()
        self.import_key()
        response = requests.post(
            '%s/droplets' % API_URL,
            headers={
                'Authorization': 'Bearer %s' % self.api_key,
                'Content-Type': 'application/json',
            },
            data=json.dumps({
                'name': DROPLET_NAME,
                'region': self.region,
                'size': DROPLET_SIZE,
                'image': DROPLET_IMAGE,
                'ssh_keys': [self.public_key_id],
            }),
        )
        if response.status_code < 200 or response.status_code >= 300:
            if response.json().get('id') == 'unauthorized':
                raise InvalidApiKey('API key is invalid')
            raise CreateDropletError('Failed to create droplet')
        self.droplet_id = response.json()['droplet']['id']

        start_time = int(time.time())
        while True:
            response = requests.get(
                '%s/droplets/%s' % (API_URL, self.droplet_id),
                headers={
                    'Authorization': 'Bearer %s' % self.api_key,
                },
            )
            if response.status_code < 200 or response.status_code >= 300:
                if response.json().get('id') == 'unauthorized':
                    raise InvalidApiKey('API key is invalid')
                raise CreateDropletError(
                    'Failed to create droplet, error getting droplet status')
            response = response.json()
            if response['droplet']['status'] == 'active':
                networks = response['droplet']['networks']['v4']
                for network in networks:
                    if network['type'] == 'public':
                        self.host = network['ip_address']
                        break
                if not self.host:
                    raise CreateDropletError('Failed to create droplet, ' + \
                        'unable to get droplet IP address')
                break
            if int(time.time()) - start_time > DROPLET_TIMEOUT:
                raise CreateDropletError(
                    'Failed to create droplet, timed out')
            time.sleep(1)
        time.sleep(5)

    def _ssh_exec(self, client, timeout, command):
        command += '; echo $?'
        start_time = int(time.time())
        stdin, stdout, stderr = client.exec_command(
            command, timeout=timeout)
        exit_code = None
        for line in stdout:
            exit_code = line.strip()
        if int(exit_code):
            raise DropletExecError('Command %r returned error exit code %s' % (
                command, exit_code))
        timeout -= (int(time.time()) - start_time)
        return max(15, timeout)

    def install(self, timeout=LOADER_TIMEOUT):
        try:
            if not self.droplet_id:
                self.create_droplet()
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(IgnorePolicy())
            for i in xrange(40):
                try:
                    client.connect(self.host, username='root',
                        pkey=self.private_key, timeout=CONNECT_TIMEOUT)
                except socket.timeout:
                    time.sleep(1)
                    if i >= 11:
                        raise DropletTimeout('SSH connection timed out')
                except:
                    time.sleep(3)
                    if i >= 11:
                        raise
            for command in (
                        'add-apt-repository -y ppa:pritunl',
                        'apt-get update -qq',
                        'apt-get install -qq -y pritunl',
                        'rm -f /root/.ssh/authorized_keys',
                    ):
                try:
                    timeout = self._ssh_exec(client, timeout, command)
                except socket.timeout:
                    raise DropletTimeout('SSH connection timed out')
            client.close()
            self.reset_password()
            time.sleep(30)
        finally:
            self.remove_key()
