"""Infrastructure layer: adapters to cloud services, persistence, and the graph DB.

The application layer depends on interfaces defined here. Concrete
implementations live in:
- adapters/aws/    : Kinesis, S3, DynamoDB, RDS
- adapters/gcp/    : Pub/Sub, GCS, Firestore, Cloud SQL
- adapters/local/  : Redpanda, MinIO, PostgreSQL (for dev)
- persistence/     : SQLAlchemy repos (cases, decisions, audit)
- graph/           : Neo4j client
"""

from src.infrastructure import adapters, graph, persistence

__all__ = ["adapters", "graph", "persistence"]
