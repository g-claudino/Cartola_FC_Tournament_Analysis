import requests
import unicodedata as ud
import json

class API:
    def __init__(self, tag, auth):
        self.tag = tag
        self.auth = auth

    def slugify(s): # Got from https://github.com/pyanderson/meu_cartola/blob/main/download.py
        n = ''.join(c for c in ud.normalize('NFD', s) if ud.category(c) != 'Mn')
        return '-'.join(n.lower().split())

    def request_api(self,query):
        url = "https://api.cartola.globo.com/" + query
        headers = {
        'Content-type': "application/json;charset=UTF-8",
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",  # noqa
        'X-GLB-APP': "cartola_web",
        'X-GLB-Auth': "oidc",
        }
        headers['X-GLB-Tag'] = str(self.tag)
        headers['Authorization'] = str(self.auth)
        res = requests.Session()
        res.encoding = 'utf-8'
        get = res.get(url, headers=headers)
        return get.json()