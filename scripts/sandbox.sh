#!/bin/bash
# Honeywell Sales Suite — Sandbox Environment Manager
# Usage: ./scripts/sandbox.sh [up|down|reset|seed|logs|status]

set -e

COMPOSE_FILE="docker-compose.sandbox.yml"
PROJECT="honeywell-sandbox"

case "${1:-help}" in
  up)
    echo "Starting sandbox environment..."
    docker compose -p "$PROJECT" -f "$COMPOSE_FILE" up -d --build
    echo ""
    echo "Sandbox is starting up. Wait ~20 seconds for services to be ready."
    echo "  Backend:  http://localhost:8001"
    echo "  Frontend: http://localhost:8081"
    echo "  Swagger:  http://localhost:8001/docs"
    echo "  Qdrant:   http://localhost:6334"
    echo ""
    echo "Login: admin@honeywell.com / Admin123!"
    echo "Run './scripts/sandbox.sh seed' to load demo data."
    ;;

  down)
    echo "Stopping sandbox..."
    docker compose -p "$PROJECT" -f "$COMPOSE_FILE" down
    echo "Sandbox stopped."
    ;;

  reset)
    echo "Resetting sandbox (deleting all data)..."
    docker compose -p "$PROJECT" -f "$COMPOSE_FILE" down -v
    echo "Starting fresh sandbox..."
    docker compose -p "$PROJECT" -f "$COMPOSE_FILE" up -d --build
    echo "Sandbox reset complete. Run './scripts/sandbox.sh seed' after ~20s."
    ;;

  seed)
    echo "Seeding sandbox with demo data..."
    docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec backend-sandbox python -m scripts.seed_demo_data
    echo "Seed complete."
    ;;

  logs)
    docker compose -p "$PROJECT" -f "$COMPOSE_FILE" logs -f backend-sandbox
    ;;

  status)
    docker compose -p "$PROJECT" -f "$COMPOSE_FILE" ps
    ;;

  help|*)
    echo "Honeywell Sales Suite — Sandbox Manager"
    echo ""
    echo "Usage: ./scripts/sandbox.sh <command>"
    echo ""
    echo "Commands:"
    echo "  up      Start sandbox (build + start all services)"
    echo "  down    Stop sandbox"
    echo "  reset   Delete all sandbox data and restart fresh"
    echo "  seed    Load demo data into sandbox"
    echo "  logs    Follow backend logs"
    echo "  status  Show container status"
    echo ""
    echo "Ports:"
    echo "  Backend:  8001  (vs production 8000)"
    echo "  Frontend: 8081  (vs production 80)"
    echo "  Postgres: 5433  (vs production 5432)"
    echo "  Redis:    6380  (vs production 6379)"
    echo "  Qdrant:   6334  (vs production 6333)"
    ;;
esac
