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

# ============================================================
# PHA v2 验收 (阶段 1-12)
# ============================================================
V2_PY ?= python
V2_VERIFY_DIR ?= scripts

.PHONY: v2-verify v2-verify-all v2-summary v2-bench v2-test v2-format v2-clean

v2-verify-all:
	@echo "=== PHA v2 全阶段验收 ==="
	@for s in 1 2 2_5 3 4 5 9 10 11 12; do \
		f="verify_stage$${s}.py"; \
		if [ -f "$(V2_VERIFY_DIR)/$$f" ]; then \
			echo "--- $$f ---"; \
			$(V2_PY) $(V2_VERIFY_DIR)/$$f || exit 1; \
		fi; \
	done
	@echo "=== 全部通过 ==="

v2-verify-%:
	@if [ -f "$(V2_VERIFY_DIR)/verify_stage$*.py" ]; then \
		$(V2_PY) $(V2_VERIFY_DIR)/verify_stage$*.py; \
	else \
		echo "No verify_stage$*.py"; \
	fi

v2-bench:
	@echo "=== 性能压测 (scripts/perf_benchmark.py) ==="
	$(V2_PY) $(V2_VERIFY_DIR)/perf_benchmark.py

v2-test:
	@echo "=== 单元测试 (pytest) ==="
	$(V2_PY) -m pytest tests/ -v || true

v2-format:
	@echo "=== 代码格式化 ==="
	$(V2_PY) -m black backend/A2AServer/src/A2AServer/v2/
	$(V2_PY) -m isort backend/A2AServer/src/A2AServer/v2/

v2-clean:
	@echo "=== 清理缓存 ==="
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# ============================================================
# 监控端点
# ============================================================
.PHONY: metrics health

metrics:
	@curl -s http://localhost:$(HOSTAPI_PORT)/metrics | head -30

health:
	@curl -s http://localhost:$(HOSTAPI_PORT)/health | head -5

