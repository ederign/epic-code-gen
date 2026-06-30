CI_IMAGE ?= quay.io/ederignatowicz/epic-code-gen-ci
CI_TAG ?= latest

.PHONY: install test test-unit test-integration clean ci-image ci-image-push ci-image-tag

install:
	uv sync

test: test-unit test-integration

test-unit:
	uv run pytest tests/ -m "not integration" -v

test-integration:
	uv run pytest tests/ -m "integration" -v

clean:
	rm -rf tmp/ .target-repo/ .context/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

CI_PLATFORMS ?= linux/amd64,linux/arm64
CI_BUILDER ?= x

ci-image:
	docker build -f Dockerfile.ci -t $(CI_IMAGE):$(CI_TAG) .

ci-image-push:
	docker buildx build --builder $(CI_BUILDER) --platform $(CI_PLATFORMS) \
		-f Dockerfile.ci -t $(CI_IMAGE):$(CI_TAG) --push .

ci-image-tag:
	$(eval GIT_SHA := $(shell git rev-parse --short HEAD))
	docker buildx build --builder $(CI_BUILDER) --platform $(CI_PLATFORMS) \
		-f Dockerfile.ci -t $(CI_IMAGE):$(CI_TAG) -t $(CI_IMAGE):$(GIT_SHA) --push .
