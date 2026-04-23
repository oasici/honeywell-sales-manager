# Honeywell Sales Manager — kisa komutlar (venv otomatik)
.PHONY: test-backend test-backend-smoke sync-backend-venv db-upgrade db-schema-audit db-ensure-aligned

# Tum backend testleri (repo kokunden; uzun surebilir)
test-backend:
	bash scripts/pytest-backend.sh tests/ -v --tb=short

# Hizli smoke (AI / conftest)
test-backend-smoke:
	bash scripts/pytest-backend.sh tests/test_v2_ai.py -v --tb=short

# requirements degistiginde
sync-backend-venv:
	bash scripts/sync-backend-venv.sh

# Postgres semasi -> Alembic head (.env DATABASE_URL; @db: otomatik 127.0.0.1)
db-upgrade:
	bash scripts/db-upgrade.sh

# Modeller vs DB tablolari/kolonlari
db-schema-audit:
	bash scripts/db-schema-audit.sh

# Denetim -> alembic upgrade head -> denetim (prod/ staging icin)
db-ensure-aligned:
	bash scripts/db-ensure-aligned.sh
