#!/usr/bin/env python3
"""Serve only disposable build output on loopback; HEAD-check preserved URLs."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from urllib.parse import quote
from urllib.request import Request, urlopen


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def check(before, after):
    urls = set()
    for directory in (before, after):
        for file in directory.rglob('*'):
            if not file.is_file():
                continue
            path = file.relative_to(directory).as_posix()
            urls.add('/' + quote(path))
            if path.endswith('index.html'):
                urls.add('/' + quote(path[:-len('index.html')]))
    urls.add('/articles/demo.html?view=full')
    handler = partial(QuietHandler, directory=str(after))
    with ThreadingHTTPServer(('127.0.0.1', 0), handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = 'http://127.0.0.1:' + str(server.server_port)
            for path in sorted(urls):
                with urlopen(Request(base + path, method='HEAD'), timeout=10) as response:
                    assert response.status == 200, path
            return {'http_200_urls': len(urls), 'includes_directory_urls_and_encoded_chinese_paths': True}
        finally:
            server.shutdown()
            thread.join()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('work_dir', type=Path)
    args = parser.parse_args()
    result = {}
    for before, after in (('legacy', 'migrated-legacy'), ('new-single', 'added-language')):
        result[before + '_to_' + after] = check(args.work_dir / before / '_site', args.work_dir / after / '_site')
    (args.work_dir / 'http-report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
