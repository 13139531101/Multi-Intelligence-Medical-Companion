SERVICES = health_records health_advisor medication_reminder visit_summary hostapi multiagent_front
REGISTRY ?= crpi-zr8m4m7ism94623a.cn-hangzhou.personal.cr.aliyuncs.com
NAMESPACE ?= duozhiyiban
IMAGE_PREFIX ?= a2aserver-
TAG ?= latest

.PHONY: build build-% tag tag-% push push-% publish publish-%

build:
	docker compose -f docker-compose.yml build $(SERVICES)

build-%:
	docker compose -f docker-compose.yml build $*

tag:
	for s in $(SERVICES); do \
		docker tag $(IMAGE_PREFIX)$$s:$(TAG) $(REGISTRY)/$(NAMESPACE)/$(IMAGE_PREFIX)$$s:$(TAG); \
	done

tag-%:
	docker tag $(IMAGE_PREFIX)$*:$(TAG) $(REGISTRY)/$(NAMESPACE)/$(IMAGE_PREFIX)$*:$(TAG)

push:
	for s in $(SERVICES); do \
		docker push $(REGISTRY)/$(NAMESPACE)/$(IMAGE_PREFIX)$$s:$(TAG); \
	done

push-%:
	docker push $(REGISTRY)/$(NAMESPACE)/$(IMAGE_PREFIX)$*:$(TAG)

publish: tag push

publish-%: tag-% push-%
