"""Pooled, retrying HTTP session for always-on polling.

Adapted from the NetworkManager pattern in
~/Development/Waveshare-ePaper-10.85-dashboard/main.py: a module that fails
to fetch should log and fall back to its last-known-good cache rather than
crash, and a session that has gone bad (e.g. after a long network drop)
should be transparently rebuilt instead of wedging future requests.
"""
import logging

import requests
from requests.adapters import HTTPAdapter, Retry

log = logging.getLogger(__name__)


class NetworkManager:
    def __init__(self):
        self.session = None
        self._create_session()

    def _create_session(self):
        if self.session:
            try:
                self.session.close()
            except Exception:
                pass
        self.session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=5,
            pool_maxsize=10,
            max_retries=Retry(total=2, backoff_factor=0.5,
                               status_forcelist=(429, 500, 502, 503, 504)),
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def get_json(self, url, headers=None, params=None, timeout=10):
        try:
            resp = self.session.get(url, headers=headers, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            log.warning("GET %s failed: %s", url, e)
            self._create_session()
            return None

    def post_json(self, url, json_body=None, headers=None, timeout=15):
        try:
            resp = self.session.post(url, json=json_body, headers=headers, timeout=timeout)
            return resp
        except requests.RequestException as e:
            log.warning("POST %s failed: %s", url, e)
            self._create_session()
            return None


net = NetworkManager()
