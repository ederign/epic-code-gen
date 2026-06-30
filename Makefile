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

ci-image:
	docker build -f Dockerfile.ci -t $(CI_IMAGE):$(CI_TAG) .

ci-image-push: ci-image
	docker push $(CI_IMAGE):$(CI_TAG)

ci-image-tag:
	$(eval GIT_SHA := $(shell git rev-parse --short HEAD))
	docker tag $(CI_IMAGE):$(CI_TAG) $(CI_IMAGE):$(GIT_SHA)
	docker push $(CI_IMAGE):$(GIT_SHA)
