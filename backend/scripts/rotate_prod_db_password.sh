#!/usr/bin/env bash
#
# Prod Postgres password rotation (Yol 2 — manuel ALTER USER).
#
# Kullanım:
#   1. Render dashboard → honeywell-db → "Info" sekmesinden
#      External Database URL'i kopyala.
#   2. Export et:
#        export RENDER_EXTERNAL_DATABASE_URL='postgresql://honeywell:ESKI_PW@dpg-xxx.oregon-postgres.render.com/honeywell_sales'
#   3. Scripti koştur:
#        bash backend/scripts/rotate_prod_db_password.sh
#
# Script şunları yapar:
#   - Yeni 32-byte URL-safe password üretir (lokal secrets.token_urlsafe).
#   - Mevcut connection string ile DB'ye bağlanıp `ALTER USER honeywell WITH
#     PASSWORD '<new>'` SQL'ini çalıştırır (dockerized psql ile).
#   - Yeni connection string'i ekrana yazar (ve yalnızca opsiyonel dosyaya).
#   - Render dashboard'a yapman gereken adımları yazdırır.
#
# Güvenlik:
#   - Yeni password stdin/stderr dışında hiçbir yere otomatik yazılmaz.
#   - Script sonunda bash history'ye eski password girmemesi için
#     komutları "history -d" ile silmeni de öneririz.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

error() { echo -e "${RED}ERROR:${NC} $*" >&2; exit 1; }
info()  { echo -e "${CYAN}→${NC} $*"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}!${NC} $*"; }

# ── 1) Guard: env var must exist ─────────────────────────────────────────────

[[ -n "${RENDER_EXTERNAL_DATABASE_URL:-}" ]] \
  || error "RENDER_EXTERNAL_DATABASE_URL export edilmemiş.

Önce:
  export RENDER_EXTERNAL_DATABASE_URL='postgresql://honeywell:...@dpg-xxx.oregon-postgres.render.com/honeywell_sales'
sonra tekrar çalıştır."

if [[ "$RENDER_EXTERNAL_DATABASE_URL" != postgresql://* ]]; then
  error "Connection string 'postgresql://' ile başlamalı."
fi

# Host must be external (render.com), not internal dpg-xxx-a (no domain)
if [[ "$RENDER_EXTERNAL_DATABASE_URL" != *render.com* ]]; then
  warn "Bu internal URL gibi duruyor. Render dashboard'dan External Database URL'i kullan."
fi

# ── 2) Check docker psql container ───────────────────────────────────────────

DOCKER_PG="honeywell-sales-manager-db-1"
if ! docker ps --filter "name=$DOCKER_PG" --format '{{.Names}}' | grep -q "$DOCKER_PG"; then
  error "Dockerized psql container '$DOCKER_PG' ayakta değil.
Önce:
  docker compose -f docker-compose.dev.yml up -d db
(veya herhangi bir postgres:16 container'ı)"
fi

# ── 3) Verify current creds work ─────────────────────────────────────────────

info "Mevcut credential ile bağlantı testi..."
if ! docker exec -i "$DOCKER_PG" \
     psql "$RENDER_EXTERNAL_DATABASE_URL" \
     -c "SELECT current_user, current_database();" >/tmp/rotate-preview.txt 2>&1; then
  cat /tmp/rotate-preview.txt >&2
  error "Mevcut connection string çalışmıyor. Password veya host yanlış olabilir."
fi
ok "Mevcut credential ile bağlanıldı:"
grep -A1 "current_user" /tmp/rotate-preview.txt | head -3
rm -f /tmp/rotate-preview.txt

# ── 4) Generate new password ─────────────────────────────────────────────────

NEW_PW="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
[[ ${#NEW_PW} -ge 30 ]] || error "Password üretimi başarısız."
ok "Yeni password üretildi (${#NEW_PW} karakter)."

# ── 5) Execute ALTER USER ────────────────────────────────────────────────────

# Parse out the user from URL (typically 'honeywell')
DB_USER="$(python3 -c "
from urllib.parse import urlparse
u = urlparse('$RENDER_EXTERNAL_DATABASE_URL')
print(u.username or 'honeywell')
")"
info "Kullanıcı: ${DB_USER}"

# Safely escape the new password for SQL (dollar-quoted string)
SQL="ALTER USER ${DB_USER} WITH PASSWORD \$\$${NEW_PW}\$\$;"

info "ALTER USER çalıştırılıyor..."
if ! docker exec -i "$DOCKER_PG" \
     psql "$RENDER_EXTERNAL_DATABASE_URL" \
     -v ON_ERROR_STOP=1 \
     -c "$SQL" > /tmp/rotate-out.txt 2>&1; then
  cat /tmp/rotate-out.txt >&2
  error "ALTER USER başarısız."
fi
ok "Password DB seviyesinde rotate edildi."
rm -f /tmp/rotate-out.txt

# ── 6) Build the new connection strings ──────────────────────────────────────

OLD_URL="$RENDER_EXTERNAL_DATABASE_URL"

NEW_EXTERNAL_URL="$(python3 -c "
from urllib.parse import urlparse, urlunparse, quote
u = urlparse('$OLD_URL')
new_netloc = f'{u.username}:{quote(\"$NEW_PW\", safe=\"\")}@{u.hostname}' + (f':{u.port}' if u.port else '')
print(urlunparse(u._replace(netloc=new_netloc)))
")"

# ── 7) Verify new password works ─────────────────────────────────────────────

info "Yeni credential ile bağlantı testi..."
if ! docker exec -i "$DOCKER_PG" \
     psql "$NEW_EXTERNAL_URL" \
     -c "SELECT 1;" >/dev/null 2>&1; then
  error "Yeni password ile bağlanamadık. ROTATION KISMEN TAMAMLANDI. DB eski password'ü KULLANMAZ artık."
fi
ok "Yeni credential çalışıyor."

# ── 8) Print next-step instructions ──────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo -e "${GREEN}ROTATION BAŞARILI.${NC} Prod backend henüz restart edilmediği için"
echo "halen eski password'ü kullanıyor — çok yakında 'authentication failed'"
echo "hatası verecek. Hemen Render env var'ını güncelle:"
echo "════════════════════════════════════════════════════════════════════"
echo ""
echo "1) Render Dashboard → honeywell-backend → Environment"
echo ""
echo "2) DATABASE_URL satırına tıkla. Eğer 'Linked to honeywell-db' yazıyorsa"
echo "   önce 'Unlink' ile blueprint sync'ini koparman gerek."
echo ""
echo "3) DATABASE_URL değerini aşağıdaki string ile değiştir:"
echo ""
echo "────────────────────────────────────────────────────────────────────"
echo "$NEW_EXTERNAL_URL"
echo "────────────────────────────────────────────────────────────────────"
echo ""
warn "Yukarıdaki satırı kopyaladıktan sonra terminal history'den sil:"
echo "    history -d \$(history 1 | awk '{print \$1}')"
echo ""
echo "4) 'Save Changes' de. Render otomatik restart tetikleyecek."
echo ""
echo "5) Rotation'ı doğrula:"
echo "    curl -s https://honeywell-backend.onrender.com/api/health | python3 -m json.tool"
echo "    # \"database\": \"ok\" görmelisin"
echo ""
echo "6) render.yaml'daki fromDatabase link'i kalırsa next blueprint sync"
echo "   eski password'ü geri basmaya çalışacak. Bunu önlemek için:"
echo "   - Ya render.yaml'daki envVars DATABASE_URL bloğunu static string'e çevir"
echo "   - Ya da periyodik rotation için 'Yol 1' (dashboard native rotate) kullan"
echo ""
echo -e "${YELLOW}Session'ı kapatmadan önce bu terminal'den \$NEW_EXTERNAL_URL çıktısını temizle.${NC}"
