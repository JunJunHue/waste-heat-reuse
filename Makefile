SITES ?= site1_chelsea site2_lansing
PY := uv run python -m heattwin.cli

.PHONY: data simulate web dev test check offline-check all clean-processed

data:            ## fetch (cached) raw data and prepare processed inputs for every site
	$(PY) data $(SITES)

simulate:        ## run the engine for every site/scenario and export to web/public/data
	$(PY) simulate $(SITES)

web:             ## build the frontend and serve it at http://localhost:4173
	cd web && npm run build && npx vite preview --port 4173 --strictPort

dev:
	cd web && npx vite --port 5173

test:
	uv run pytest -q

check:           ## build + headless render check (no external requests, no console errors, screenshot)
	cd web && npm run build && (npx vite preview --port 4173 --strictPort >/dev/null 2>&1 & echo $$! > .preview.pid) && sleep 2 && \
	  node scripts/check.mjs; status=$$?; kill `cat .preview.pid`; rm -f .preview.pid; exit $$status

offline-check: check

all: data simulate test check

clean-processed:
	rm -rf data/processed web/public/data
