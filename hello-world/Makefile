# Images of the Hello World modules: make images [REGISTRY=localhost:5001] ; make push
include ../versions.env

REGISTRY ?= localhost:5001
VERSION  ?= 0.1.0
MODULES  := init hello world exclaim
DOCKER   ?= docker

.PHONY: images push manifests
images: ## build mf-hello-<module>:$(VERSION) for all four modules
	@for m in $(MODULES); do \
	  echo "==> $(REGISTRY)/mf-hello-$$m:$(VERSION)"; \
	  $(DOCKER) build --build-arg MODULE=$$m --build-arg SDK_REPO=$(SDK_REPO) --build-arg SDK_REF=$(SDK_REF) \
	    -t $(REGISTRY)/mf-hello-$$m:$(VERSION) . || exit 1; \
	done

push: images ## push the images to $(REGISTRY)
	@for m in $(MODULES); do $(DOCKER) push $(REGISTRY)/mf-hello-$$m:$(VERSION) || exit 1; done

manifests: ## smoke test: every image starts Python, imports the SDK and loads its module
	@for m in $(MODULES); do \
	  $(DOCKER) run --rm $(REGISTRY)/mf-hello-$$m:$(VERSION) mf-module manifest main:app >/dev/null || exit 1; \
	  echo "ok $(REGISTRY)/mf-hello-$$m:$(VERSION)"; \
	done
