include versions.env

UV ?= uv
GOBIN ?= $(CURDIR)/.bin
MANUFACTURE := $(GOBIN)/manufacture

.PHONY: help sync lint fmt typecheck test fakecore validate check
help: ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

sync: ## install the pinned SDK and dev tools
	$(UV) sync --locked

lint: ## ruff check + format check
	$(UV) run ruff check .
	$(UV) run ruff format --check .

fmt: ## format and autofix
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

typecheck: ## mypy --strict
	$(UV) run mypy

test: ## module unit tests (manufacture.testing, no broker)
	$(UV) run pytest

HELLO_MODULES := $(foreach m,init hello world exclaim,hello-world/modules/$(m)/main.py)

fakecore: ## Hello World end-to-end on the SDK fake core (in-memory broker; BROKER=amqp for RabbitMQ)
	$(UV) run mf-fakecore -f hello-world/pipeline.yaml $(HELLO_MODULES) --broker $(or $(BROKER),memory) \
	  --timeout 60 -o .fakecore-runs.json
	@$(UV) run python -c 'import json,sys; [r] = json.load(open(".fakecore-runs.json")); \
	  print(r["status"], r["data"]); sys.exit(r["data"] != {"text": "hello world!"})'

$(MANUFACTURE): versions.env
	GOBIN=$(GOBIN) go install github.com/t1menar/manufacture-core/cmd/manufacture@$(CORE_REF)
	@touch $@

validate: $(MANUFACTURE) ## manufacture validate --strict on every example (core pinned by CORE_REF)
	$(MANUFACTURE) validate --strict -f hello-world/

check: lint typecheck test validate ## everything CI runs
