#!/usr/bin/env bash
# One-command local startup. Spins up the Docker stack, waits for health,
# initializes the database schema and Neo4j constraints, and prints URLs.

set -euo pipefail

cd "$(dirname "$0")/.."

# 1. Start the stack
docker compose up -d

# 2. Wait for the API to be ready
echo "Waiting for API at http://localhost:8000/api/health ..."
for i in {1..30}; do
  if curl -s --max-time 2 http://localhost:8000/api/health > /dev/null; then
    echo "API ready."
    break
  fi
  sleep 2
done

# 3. Initialize the Postgres schema
python -c "from src.infrastructure.persistence import init_db; init_db()"

# 4. Initialize the Neo4j schema
python -c "from src.infrastructure.graph import get_graph_client; g = get_graph_client(); g.init_schema(); print('Neo4j schema initialized')"

cat <<EOF

=========================================
 Identity Intelligence Platform — running
=========================================
 API:       http://localhost:8000/docs
 UI:        http://localhost:8501
 MLflow:    http://localhost:5000
 Neo4j:     http://localhost:7474  (neo4j / password)
 Redpanda:  localhost:9092
 MinIO:     http://localhost:9001  (minioadmin / minioadmin)
 Postgres:  localhost:5432         (idintel / idintel)

 Generate events:
   make generate-all
EOF
