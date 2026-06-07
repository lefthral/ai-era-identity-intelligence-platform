"""Graph layer: Neo4j client and identity resolution.

The identity graph is the substrate that makes the platform a
"identity intelligence" platform rather than a generic fraud detector.

In production this would be Neo4j Aura (free tier) or a self-hosted
Neo4j Enterprise cluster. For local dev we use Neo4j Community.
"""

from src.infrastructure.graph.client import GraphClient, get_graph_client

__all__ = ["GraphClient", "get_graph_client"]
