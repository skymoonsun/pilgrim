# ─────────────────────────────────────────────────────────────────
# Pilgrim — Makefile
# ─────────────────────────────────────────────────────────────────

.PHONY: help dev dev-build dev-down dev-logs dev-ps \
        migrate migrate-create migrate-downgrade \
        seed seed-status \
        shell db-shell redis-shell \
        test lint \
        prod prod-build prod-down \
        clean

COMPOSE_DEV = docker compose -f docker-compose.dev.yml
COMPOSE_PROD = docker compose -f docker-compose.yml

# ── Help ─────────────────────────────────────────────────────────
help: ## Bu yardım mesajını göster
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Development ──────────────────────────────────────────────────
dev: ## Dev stack'i başlat (build olmadan)
	$(COMPOSE_DEV) up -d

dev-build: ## Dev stack'i build edip başlat
	$(COMPOSE_DEV) up -d --build

dev-down: ## Dev stack'i durdur (volume'ları koru)
	$(COMPOSE_DEV) down

dev-reset: ## Dev stack'i durdur ve volume'ları sil
	$(COMPOSE_DEV) down -v

dev-logs: ## Tüm servislerin loglarını takip et
	$(COMPOSE_DEV) logs -f

dev-logs-api: ## Sadece API loglarını takip et
	$(COMPOSE_DEV) logs -f api

dev-logs-worker: ## Sadece worker loglarını takip et
	$(COMPOSE_DEV) logs -f worker

dev-ps: ## Çalışan servisleri listele
	$(COMPOSE_DEV) ps

dev-restart: ## API servisini yeniden başlat
	$(COMPOSE_DEV) restart api

# ── Database Migrations ──────────────────────────────────────────
migrate: ## Migration'ları uygula (alembic upgrade head)
	$(COMPOSE_DEV) exec api alembic upgrade head

migrate-create: ## Yeni migration oluştur (kullanım: make migrate-create MSG="açıklama")
	$(COMPOSE_DEV) exec api alembic revision --autogenerate -m "$(MSG)"

migrate-downgrade: ## Son migration'ı geri al
	$(COMPOSE_DEV) exec api alembic downgrade -1

migrate-history: ## Migration geçmişini görüntüle
	$(COMPOSE_DEV) exec api alembic history --verbose

# ── Seeds ────────────────────────────────────────────────────────
seed: ## Pending seed'leri uygula
	$(COMPOSE_DEV) exec api python -m app.cli.seed

seed-status: ## Seed durumunu görüntüle
	$(COMPOSE_DEV) exec api python -m app.cli.seed --status

setup: migrate seed ## Migration + seed'leri sırayla uygula

# ── Shell Access ─────────────────────────────────────────────────
shell: ## API container'ında Python shell aç
	$(COMPOSE_DEV) exec api python

db-shell: ## PostgreSQL shell aç
	$(COMPOSE_DEV) exec postgres psql -U pilgrim -d pilgrim

redis-shell: ## Redis CLI aç
	$(COMPOSE_DEV) exec redis redis-cli

bash: ## API container'ında bash shell aç
	$(COMPOSE_DEV) exec api bash

# ── Testing ──────────────────────────────────────────────────────
test: ## Testleri çalıştır
	$(COMPOSE_DEV) exec api pytest -v

test-cov: ## Testleri coverage ile çalıştır
	$(COMPOSE_DEV) exec api pytest --cov=app --cov-report=html -v

# ── Linting ──────────────────────────────────────────────────────
lint: ## Kod kalitesi kontrolü (ruff)
	$(COMPOSE_DEV) exec api ruff check app/

format: ## Kodu formatla (ruff)
	$(COMPOSE_DEV) exec api ruff format app/

# ── Production ───────────────────────────────────────────────────
prod: ## Production stack'i başlat
	$(COMPOSE_PROD) up -d

prod-build: ## Production stack'i build edip başlat
	$(COMPOSE_PROD) up -d --build

prod-down: ## Production stack'i durdur
	$(COMPOSE_PROD) down

# ── Cleanup ──────────────────────────────────────────────────────
clean: ## Docker cache ve dangling image'ları temizle
	docker system prune -f
	docker volume prune -f
