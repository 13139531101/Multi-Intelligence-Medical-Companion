SERVICES = health_records health_advisor medication_reminder visit_summary hostapi admin_backend admin_frontend
REGISTRY ?= crpi-zr8m4m7ism94623a.cn-hangzhou.personal.cr.aliyuncs.com
NAMESPACE ?= duozhiyiban
IMAGE_PREFIX ?= a2aserver-
TAG ?= latest
ifeq ($(OS),Windows_NT)
COMPOSE = set "REGISTRY=$(REGISTRY)" && set "NAMESPACE=$(NAMESPACE)" && set "IMAGE_PREFIX=$(IMAGE_PREFIX)" && set "TAG=$(TAG)" && docker compose -f docker-compose.yml
else
COMPOSE = REGISTRY=$(REGISTRY) NAMESPACE=$(NAMESPACE) IMAGE_PREFIX=$(IMAGE_PREFIX) TAG=$(TAG) docker compose -f docker-compose.yml
endif

.PHONY: build build-% pull pull-% up up-% tag tag-% push push-% publish publish-%

build:
	$(COMPOSE) build $(SERVICES)

build-%:
	$(COMPOSE) build $*

pull:
	$(COMPOSE) pull $(SERVICES)

pull-%:
	$(COMPOSE) pull $*

up: pull
	$(COMPOSE) up -d --no-build $(SERVICES)

up-%: pull-%
	$(COMPOSE) up -d --no-build $*

tag:
	@echo "skip tag: images are built with repository names directly"

tag-%:
	@echo "skip tag-$*: image already uses repository name"

push: $(addprefix push-,$(SERVICES))

push-%:
	docker push $(REGISTRY)/$(NAMESPACE)/$(IMAGE_PREFIX)$*:$(TAG)

publish: tag push

publish-%: tag-% push-%
