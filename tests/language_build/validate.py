#!/usr/bin/env python3
"""Generate disposable sites, run real GitBook builds, audit published paths."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit, urljoin
import xml.etree.ElementTree as ET

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from language_layout import CSS_URL

SITE_URL = 'https://fixture.invalid/'
CONTENT = ('README.md', 'SUMMARY.md', 'articles', 'assets', '.well-known')


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def config_for(repo):
    config = json.loads((repo / 'book.json').read_text())
    config.update(title='中文验证站点', description='Language build fixture', language='zh-hans')
    plugins = config['pluginsConfig']
    # Preserve real plugins, but never embed real analytics IDs or business URLs.
    plugins['3-ba'] = {'token': 'fixture-not-a-real-token'}
    plugins['ga4'] = {'tag': 'G-FIXTURE'}
    plugins['logo']['url'] = SITE_URL
    plugins['edit-link']['base'] = 'https://github.com/example/fixture/blob/main'
    plugins['canonical-link']['baseURL'] = SITE_URL.rstrip('/')
    plugins['seenical'].update(sitemap_hostname=SITE_URL, footer_note='Fixture footer', lanying_link='')
    plugins['tbfed-pagefooter']['copyright'] = 'Fixture copyright'
    return config


def add_content(path, repo, language):
    path.mkdir(parents=True, exist_ok=True)
    template_assets = repo / 'zh-hans/assets'
    if not template_assets.is_dir():
        template_assets = repo / 'assets'
    shutil.copytree(template_assets, path / 'assets')
    (path / 'articles/section').mkdir(parents=True)
    (path / '.well-known').mkdir()
    (path / '.well-known/fixture.txt').write_text('public fixture attachment\n')
    marker = 'ChineseFixture' if language == 'zh-hans' else 'EnglishFixture'
    (path / 'README.md').write_text('# ' + marker + '\n\n[Demo](articles/demo.md)\n\n![Logo](assets/logo.png)\n')
    (path / 'SUMMARY.md').write_text('* [Home](README.md)\n* [Demo](articles/demo.md)\n* [Section](articles/section/README.md)\n  * [Detail](articles/section/detail.md)\n* [中文路径](articles/中文.md)\n')
    (path / 'articles/demo.md').write_text('# ' + marker + ' demo\n\n## Details\n\n[Home](../README.md)\n\n[Nested](section/detail.md?view=full#details)\n\n[中文](中文.md)\n\n![Logo](../assets/logo.png)\n\n[Existing absolute URL](/articles/demo.html#details)\n\n[Attachment](/.well-known/fixture.txt)\n')
    (path / 'articles/section/README.md').write_text('# Section\n')
    (path / 'articles/section/detail.md').write_text('# Detail\n\n## Details\n\n' + marker + ' nested content\n\n[Demo](../demo.md#details)\n\n![Logo](../../assets/logo.png)\n')
    (path / 'articles/中文.md').write_text('# 中文路径\n\n' + marker + '\n')


def scaffold(site, repo, config):
    site.mkdir()
    write_json(site / 'book.json', config)
    shutil.copytree(repo / 'scripts', site / 'scripts')
    (site / '.bookignore').write_text('_site*/\n_book/\nnode_modules/\nscripts/\n*.log\nsite-layout.json\nMakefile\n')
    (site / 'Makefile').write_text('''GITBOOK ?= gitbook
OUTPUT ?= _site
.PHONY: build refine
build:
	$(GITBOOK) build
	$(MAKE) refine
refine:
	python3 scripts/subdirectory_summary.py --site-dir .
	python3 scripts/language_layout.py _book $(OUTPUT)
''')


def language_config(site, language, config):
    localized = json.loads(json.dumps(config))
    localized['language'] = language
    localized['title'] = '中文验证站点' if language == 'zh-hans' else 'English validation site'
    prefix = '' if language == 'zh-hans' else '/en'
    localized['pluginsConfig']['canonical-link']['baseURL'] = SITE_URL.rstrip('/') + prefix
    localized['pluginsConfig']['edit-link']['base'] += '/' + language
    write_json(site / language / 'book.json', localized)


def languages(site, codes):
    (site / 'LANGS.md').write_text(''.join('* [{}]({}/)\n'.format(code, code) for code in codes))
    # A small native template override tests cross-language navigation. Links
    # must be inserted at template-render time: GitBook rewrites root-relative
    # links in Markdown/page-footer content relative to the language source root.
    for code in codes:
        layout = site / code / '_layouts/website'
        layout.mkdir(parents=True, exist_ok=True)
        links = ''.join('<a class="fixture-language" href="/{}/">{}</a>'.format(target, target) for target in codes)
        (layout / 'page.html').write_text('{% extends template.self %}\n{% block page %}{{ super() }}<nav aria-label="Fixture languages">' + links + '</nav>{% endblock %}\n')
    write_json(site / 'site-layout.json', {'default_language': 'zh-hans', 'languages': {code: {'source_dir': code, 'public_path': '/' if code == 'zh-hans' else '/' + code + '/'} for code in codes}})


def copy_content(source, destination):
    for name in CONTENT:
        src, dst = source / name, destination / name
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
        self.canonical = []
        self.basepaths = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('rel') == 'canonical':
            self.canonical.append(attrs.get('href'))
        for name in ('href', 'src', 'poster'):
            if name in attrs:
                self.urls.append(attrs[name])
        if 'data-basepath' in attrs:
            self.basepaths.append(attrs['data-basepath'])


def resolve_local(root, page, value):
    parsed = urlsplit(value)
    if parsed.netloc or parsed.scheme or not parsed.path:
        return None
    url = urljoin('/' + page, unquote(parsed.path))
    path = root / url.lstrip('/')
    if path.is_dir():
        path /= 'index.html'
    return path


def audit(root):
    broken, canonicals, links_checked = [], {}, 0
    for file in sorted(root.rglob('*.html')):
        name = file.relative_to(root).as_posix()
        parser = Links()
        parser.feed(file.read_text())
        canonicals[name] = parser.canonical
        for value in parser.urls:
            target = resolve_local(root, name, value)
            if target is not None:
                links_checked += 1
                if not target.is_file():
                    broken.append('{} -> {}'.format(name, value))
        for base in parser.basepaths:
            base_url = urljoin('/' + name, base.rstrip('/') + '/')
            if not (root / base_url.lstrip('/')).is_dir():
                broken.append('{} basepath -> {}'.format(name, base))
    for file in root.rglob('*.css'):
        name = file.relative_to(root).as_posix()
        for match in CSS_URL.finditer(file.read_text()):
            target = resolve_local(root, name, match['url'])
            if target is not None:
                links_checked += 1
                if not target.is_file():
                    broken.append('{} CSS -> {}'.format(name, match['url']))
    sitemap_urls = []
    for file in root.rglob('*sitemap*.xml'):
        for element in ET.fromstring(file.read_text()).iter():
            if element.tag.split('}')[-1] != 'loc':
                continue
            url = element.text
            sitemap_urls.append(url)
            path = urlsplit(url).path
            if urlsplit(url).netloc == 'fixture.invalid':
                target = root / unquote(path).lstrip('/')
                if target.is_dir():
                    target /= 'index.html'
                if not target.is_file():
                    broken.append('{} sitemap -> {}'.format(file.name, url))
    if broken:
        raise AssertionError('Broken local references:\n' + '\n'.join(broken[:40]))
    return {'html_pages': len(canonicals), 'local_references_checked': links_checked, 'canonicals': canonicals, 'sitemap_urls': sitemap_urls}


def run(command, site, name):
    with (site / (name + '.log')).open('w') as log:
        result = subprocess.run(command, cwd=site, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError('{} failed: {}'.format(command, site / (name + '.log')))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--work-dir', type=Path, required=True, help='Must not exist; generated sources and outputs are retained')
    parser.add_argument('--gitbook', default='gitbook')
    parser.add_argument('--plugin-dir', type=Path, help='Reuse already installed real template plugins (node_modules)')
    parser.add_argument('--with-search', action='store_true', help='Also exercise native GitBook search/lunr, disabled in the production template')
    args = parser.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=False)
    config = config_for(args.repo)
    if args.with_search:
        config['plugins'] = [p for p in config['plugins'] if p not in ('-search', '-lunr')]
    report = {'gitbook': '3.2.3', 'search_enabled_for_validation': args.with_search, 'cases': {}}
    baseline = args.work_dir / 'legacy'
    scaffold(baseline, args.repo, config)
    add_content(baseline, args.repo, 'zh-hans')
    new = args.work_dir / 'new-single'
    scaffold(new, args.repo, config)
    add_content(new / 'zh-hans', args.repo, 'zh-hans')
    language_config(new, 'zh-hans', config)
    languages(new, ['zh-hans'])
    added = args.work_dir / 'added-language'
    scaffold(added, args.repo, config)
    shutil.copytree(new / 'zh-hans', added / 'zh-hans')
    add_content(added / 'en', args.repo, 'en')
    language_config(added, 'en', config)
    languages(added, ['zh-hans', 'en'])
    migrated = args.work_dir / 'migrated-legacy'
    scaffold(migrated, args.repo, config)
    (migrated / 'zh-hans').mkdir()
    copy_content(baseline, migrated / 'zh-hans')
    language_config(migrated, 'zh-hans', config)
    add_content(migrated / 'en', args.repo, 'en')
    language_config(migrated, 'en', config)
    languages(migrated, ['zh-hans', 'en'])
    for name in CONTENT:
        a, b = baseline / name, migrated / 'zh-hans' / name
        equal = hashes(a) == hashes(b) if a.is_dir() else a.read_bytes() == b.read_bytes()
        assert equal, name
    report['migration_source_bytes_preserved'] = True
    for site in (baseline, new, added, migrated):
        print('Building ' + site.name, flush=True)
        if args.plugin_dir:
            (site / 'node_modules').symlink_to(args.plugin_dir.resolve(), target_is_directory=True)
        else:
            run([args.gitbook, 'install'], site, 'install')
        # This is the real native CLI, without an alternative compiler or mock.
        run([args.gitbook, 'build'], site, 'build')
        run(['python3', 'scripts/subdirectory_summary.py', '--site-dir', '.'], site, 'summaries')
        if site == baseline:
            shutil.copytree(site / '_book', site / '_site')
        else:
            # Execute the same standalone post-build command distributed with the sample.
            run(['python3', 'scripts/language_layout.py', '_book', '_site'], site, 'refine')
        result = audit(site / '_site')
        for page in ('index.html', 'articles/demo.html', 'articles/中文.html', 'articles/section/index.html', 'articles/section/detail.html'):
            assert 'ChineseFixture' in (site / '_site' / page).read_text() or page.endswith('section/index.html'), page
        if site in (added, migrated):
            assert 'EnglishFixture' in (site / '_site/en/index.html').read_text()
        if site in (added, migrated):
            for page in ('index.html', 'en/index.html', 'articles/demo.html', 'en/articles/demo.html'):
                parser = Links()
                parser.feed((site / '_site' / page).read_text())
                assert '/' in parser.urls and '/en/' in parser.urls, 'language links missing'
            result['language_home_links_verified'] = True
        report['cases'][site.name] = result
    # Every previously public file must remain available, not just selected URLs.
    for before, after in ((baseline, migrated), (new, added)):
        old, now = hashes(before / '_site'), hashes(after / '_site')
        missing = sorted(set(old) - set(now))
        assert not missing, missing
        resources = [p for p in old if p.startswith(('assets/', '.well-known/'))]
        assert all(old[p] == now[p] for p in resources), 'resource bytes changed'
        for page, canonical in report['cases'][before.name]['canonicals'].items():
            assert report['cases'][after.name]['canonicals'][page] == canonical, 'canonical changed: ' + page
        report[before.name + '_to_' + after.name] = {'old_public_files_preserved': len(old), 'resource_bytes_preserved': len(resources), 'canonical_urls_preserved': True}
    # Also exercise the documented one-command local build and compare its output.
    run(['make', 'build', 'GITBOOK=' + args.gitbook, 'OUTPUT=_site-repeat'], added, 'repeat-build')
    assert set(hashes(added / '_site')) == set(hashes(added / '_site-repeat'))
    audit(added / '_site-repeat')
    report['make_build_repeat_paths_preserved'] = True
    if args.with_search:
        # Diagnose the native plugin separately: a localization failure must not
        # be hidden by a successful build or attributed to output relocation.
        script = r'''
const fs = require('fs');
const plugin = process.argv[1];
const lunr = require(require.resolve('lunr', {paths: [plugin]}));
const root = process.argv[2];
let result = {};
for (const file of ['_book/zh-hans/search_index.json', '_book/en/search_index.json', '_site/search_index.json', '_site/en/search_index.json']) {
    const data = JSON.parse(fs.readFileSync(root + '/' + file));
    const idx = lunr.Index.load(data.index);
    result[file] = {};
    for (const term of ['ChineseFixture', 'EnglishFixture']) result[file][term] = idx.search(term).map(r => r.ref);
}
console.log(JSON.stringify(result));
'''
        # Resolve the same lunr package loaded by the installed native GitBook.
        gitbook_version = subprocess.check_output([args.gitbook, 'ls'], text=True)
        report['gitbook_versions'] = gitbook_version
        cache = os.environ.get('GITBOOK_DIR', str(Path.home() / '.gitbook'))
        plugin_path = str((Path(cache) / 'versions/3.2.3').resolve() / 'node_modules/gitbook-plugin-lunr')
        diagnostic = json.loads(subprocess.check_output(['node', '-e', script, plugin_path, str(added)], text=True))
        assert diagnostic['_book/zh-hans/search_index.json'] == diagnostic['_site/search_index.json']
        assert diagnostic['_book/en/search_index.json'] == diagnostic['_site/en/search_index.json']
        assert diagnostic['_site/search_index.json']['ChineseFixture']
        assert diagnostic['_site/en/search_index.json']['EnglishFixture']
        report['search_diagnostic'] = diagnostic
        if diagnostic['_site/en/search_index.json']['ChineseFixture']:
            report['known_limitations'] = ['Native lunr mixes Chinese terms into the English index before postprocessing; production template disables lunr/search.']
    write_json(args.work_dir / 'report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
