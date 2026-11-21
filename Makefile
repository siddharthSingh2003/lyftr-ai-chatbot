.PHONY: up down logs restart test dev-backend dev-frontend check-env

up: check-env
	docker compose up --build -d
	@echo "backend:  http://localhost:$${BACKEND_PORT:-8000}"
	@echo "frontend: http://localhost:$${FRONTEND_PORT:-3000}"

down:
	docker compose down

logs:
	docker compose logs -f

restart:
	docker compose restart backend

test:
	cd backend && python -m pytest -q

check-env:
	@test -f .env || (echo "Missing .env - run: cp .env.example .env  (then add 2+ real keys)" && exit 1)
