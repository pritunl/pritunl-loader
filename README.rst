pritunl-loader: automated pritunl installer
===========================================

Heroku app for pritunl used to automatically install heroku on DigitalOcean
droplets using API tokens.

Setup
-----

.. code-block:: bash

    $ heroku create
    $ heroku config:set API_KEY=<api_key>
    $ heroku config:set REDIS_URL=<redis_url>
    $ heroku config:set ORIGIN_URL=<origin_url>
    $ git push heroku master
