GITBOOK ?= gitbook

.PHONY: build serve refine package

build:
	$(GITBOOK) build
	$(MAKE) refine

serve:
	$(GITBOOK) serve --log=debug --debug --no-live

refine:
	python3 scripts/subdirectory_summary.py --site-dir .
	python3 scripts/language_layout.py

package: build
	tar -czf book.tar.gz -C .build _book
