.PHONY: dev start migrate makemigrations install

# Install dependencies
install:
	pip install -r requirements.txt

# Run development server
dev:
	./venv/bin/uvicorn app.main:app --reload --port 5208

# Run production server
start:
	./venv/bin/uvicorn app.main:app --port 5208

# Run database migrations
migrate:
	./venv/bin/alembic upgrade head

# Create new migration (usage: make makemigrations MESSAGE="your message")
makemigrations:
	./venv/bin/alembic revision --autogenerate -m "$(MESSAGE)"

