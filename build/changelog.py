#!/usr/bin/env python
from __future__ import print_function

import os
import sys
import json
import base64
import datetime

if sys.version_info.major < 3:
    reload(sys)
    sys.setdefaultencoding('utf8')

try:
    import urllib3
    http = urllib3.PoolManager()
    def makereq(url, headers):
        return http.request('GET', url, headers=headers)
except ImportError:
    import urllib2 as request
    class MyResponse:
        def __init__(self, status, data):
            self.status = status
            self.data = data
    def makereq(url, headers):
        f = request.urlopen(request.Request(url, headers=headers))
        return MyResponse(f.getcode(), f.read().decode('utf-8'))


if 'fromisoformat' in dir(datetime.datetime):
    def get_time(s):
        return datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))
else:
    try:
        from dateutil.parser import parser
        def get_time(s):
            return parser().parse(s)
    except ImportError:
        def get_time(s):
            return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


GITHUB_AUTH = None
tok = os.getenv('GITHUB_TOKEN')
usn = os.getenv('GITHUB_USERNAME')
psw = os.getenv('GITHUB_PASSWORD')
if tok is not None:
    GITHUB_AUTH = f'token {tok}'
elif usn is not None and psw is not None:
    GITHUB_AUTH = f"Basic {base64.b64encode(f'{usn}:{psw}'.encode('utf-8')).decode('utf-8')}"

def get(url):
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'zjunet-build-agent/0.1',
    }
    if GITHUB_AUTH is not None:
        headers['Authorization'] = GITHUB_AUTH
    r = makereq(url, headers=headers)
    assert (
        r.status // 100 == 2
    ), f'HTTP Status {r.status} != 2xx while requesting {url}'
    if r.status != 200:
        print(f'WARNING: HTTP {r.status} while requesting {url}')
    return r.data

def api_get(url):
    return json.loads(get(f'https://api.github.com/{url}'))

author_cache = {}
def get_author(name):
    if name in author_cache:
        return author_cache[name]
    print(f'Reading data for {name}', end=' : ', file=sys.stderr)
    data = api_get(f'users/{name}')
    data = {
        'name': data['name'],
        'email': data['email'],
    }
    author_cache[name] = data
    print(f"{data['name']} <{data['email']}>", file=sys.stderr)
    return data

def get_changelog(owner, name):
    print('Reading releases of {1} in {0}'.format(owner, name), file=sys.stderr)
    releases = api_get(f'repos/{owner}/{name}/releases')
    releases = filter(lambda v: not v['draft'] and not v['prerelease'], releases)

    data = []
    for rel in releases:
        name = rel['name'] or rel['tag_name']
        item = {
            'time': get_time(rel['published_at']),
            'name': name,
            'version': name[name.rfind('v') + 1:].split(','),
            'author': get_author(rel['author']['login']),
            'changes': None,
        }
        tbody = rel['body'].strip()
        if tbody != '':
            item['changes'] = tbody if tbody[0] == '-' or '\n' in tbody else f'- {tbody}'
        data.append(item)
    return ChangeLog(data)

class ChangeLog:
    def __init__(self, data):
        self.raw = data
    def rpm(self):
        rel = '%changelog\n'
        for item in self.raw:
            rel += f"* {item['time'].strftime('%a %b %d %Y')} {item['author']['name']} <{item['author']['email']}> - {'.'.join(item['version'])}\n"
            if item['changes'] is not None:
                rel += item['changes'] + '\n'
        return rel

available_formats = list(filter(lambda v: v[0] != '_', dir(ChangeLog)))

if len(sys.argv) != 2:
    print(
        f"Usage: {sys.argv[0]} <format>\nAvailable formats: {','.join(available_formats)}"
    )
else:
    changelog = get_changelog('QSCTech', 'zjunet')
    if hasattr(changelog, sys.argv[1]):
        print(getattr(changelog, sys.argv[1])())
    else:
        print('Invalid format {}\nAvailable formats: {}'.format(','.join(available_formats)))
