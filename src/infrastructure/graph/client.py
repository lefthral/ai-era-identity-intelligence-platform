"""Neo4j client and identity resolution.

Uses py2neo for the local/dev path; same Cypher works for Neo4j Aura.
The graph is queried by the API to render entity subgraphs in the UI
and by the FeatureComputer to get shared-device / mule-ring signals.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from src.application.schemas import GraphEdge, GraphNode, GraphResponse

logger = logging.getLogger(__name__)


class GraphClient:
    def __init__(
        self, uri: str | None = None, user: str | None = None, password: str | None = None
    ):
        self.uri = (
            uri or os.getenv("NEO4J_URI") or os.getenv("LOCAL_NEO4J_URI", "bolt://localhost:7687")
        )
        self.user = user or os.getenv("NEO4J_USER") or os.getenv("LOCAL_NEO4J_USER", "neo4j")
        self.password = (
            password
            or os.getenv("NEO4J_PASSWORD")
            or os.getenv("LOCAL_NEO4J_PASSWORD", "localdevpassword")
        )
        self._driver = None
        self._in_memory_fallback: dict[str, dict] = {}
        self._use_fallback = False

    def _ensure_driver(self):
        if self._driver is not None:
            return self._driver
        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            with self._driver.session() as session:
                session.run("RETURN 1").single()
            logger.info("Connected to Neo4j at %s", self.uri)
            return self._driver
        except Exception as e:
            logger.warning("Neo4j unavailable (%s); using in-memory fallback", e)
            self._use_fallback = True
            return None

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    # ── Schema management ────────────────────────────────────────────────

    def init_schema(self) -> None:
        driver = self._ensure_driver()
        if driver is None:
            return
        constraints = [
            "CREATE CONSTRAINT person_id IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT account_id IF NOT EXISTS FOR (a:Account) REQUIRE a.id IS UNIQUE",
            "CREATE CONSTRAINT device_fp IF NOT EXISTS FOR (d:Device) REQUIRE d.fingerprint IS UNIQUE",
            "CREATE CONSTRAINT ip_addr IF NOT EXISTS FOR (i:IP) REQUIRE i.address IS UNIQUE",
            "CREATE CONSTRAINT mule_ring_id IF NOT EXISTS FOR (m:MuleRing) REQUIRE m.id IS UNIQUE",
        ]
        with driver.session() as session:
            for stmt in constraints:
                try:
                    session.run(stmt)
                except Exception as e:
                    logger.debug("Constraint issue: %s", e)

    # ── Write paths ─────────────────────────────────────────────────────

    def upsert_event(self, event) -> None:
        """Write a PaymentEvent into the graph (MERGE all entities + relationships)."""
        driver = self._ensure_driver()
        if driver is None:
            return self._upsert_in_memory(event)
        actor = event.actor
        cp = event.counterparty
        cypher = """
        MERGE (p:Person {id: $person_id})
          ON CREATE SET p.created_at = datetime()
        MERGE (a:Account {id: $account_id})
          ON CREATE SET a.created_at = datetime(), a.opened_at = datetime()
          SET a.country_code = $actor_country, a.is_mule = false
        MERGE (p)-[:OWNS]->(a)
        WITH p, a, $device_fp AS dfp
        FOREACH (_ IN CASE WHEN dfp IS NOT NULL THEN [1] ELSE [] END |
          MERGE (d:Device {fingerprint: dfp})
            ON CREATE SET d.first_seen = datetime()
            SET d.last_seen = datetime()
          MERGE (p)-[:USED_DEVICE]->(d)
          MERGE (a)-[:USED_ON]->(d)
        )
        WITH p, a, $ip AS ip
        FOREACH (_ IN CASE WHEN ip IS NOT NULL THEN [1] ELSE [] END |
          MERGE (i:IP {address: ip})
            ON CREATE SET i.first_seen = datetime()
            SET i.last_seen = datetime()
          MERGE (p)-[:FROM_IP]->(i)
        )
        WITH p, a
        MERGE (cp:Account {id: $cp_account_id})
          ON CREATE SET cp.created_at = datetime(), cp.opened_at = datetime() - duration({days: $cp_age_days}),
                        cp.country_code = $cp_country, cp.is_mule = $cp_is_mule
        MERGE (a)-[r:TRANSFERRED_TO]->(cp)
          ON CREATE SET r.count = 0, r.total_amount = 0.0
          SET r.count = r.count + 1,
              r.total_amount = r.total_amount + $amount,
              r.last_at = datetime()
        """
        with driver.session() as session:
            session.run(
                cypher,
                {
                    "person_id": str(actor.person_id),
                    "account_id": str(actor.account_id),
                    "actor_country": actor.country_code,
                    "device_fp": actor.device.fingerprint if actor.device else None,
                    "ip": actor.ip.address if actor.ip else None,
                    "cp_account_id": str(cp.account_id),
                    "cp_country": cp.country_code,
                    "cp_age_days": cp.account_age_days,
                    "cp_is_mule": (
                        bool(getattr(cp.account, "is_mule", False)) if cp.account else False
                    ),
                    "amount": float(event.amount.value),
                },
            )
        return None

    def _upsert_in_memory(self, event) -> None:
        # Minimal in-memory model for offline operation
        actor_id = str(event.actor.account_id)
        cp_id = str(event.counterparty.account_id)
        self._in_memory_fallback.setdefault(
            actor_id, {"type": "Account", "id": actor_id, "edges": []}
        )
        self._in_memory_fallback.setdefault(cp_id, {"type": "Account", "id": cp_id, "edges": []})
        self._in_memory_fallback[actor_id]["edges"].append(
            {"to": cp_id, "amount": float(event.amount.value)}
        )

    # ── Read paths ──────────────────────────────────────────────────────

    def get_subgraph(self, entity_id: str, depth: int = 2) -> GraphResponse:
        driver = self._ensure_driver()
        if driver is None:
            return self._subgraph_in_memory(entity_id, depth)
        cypher = f"""
        MATCH (n {{id: $entity_id}})-[*1..{depth}]-(m)
        RETURN DISTINCT n, m, labels(n) AS lns, labels(m) AS lms,
               [(n)-[r]->(m) | {{type: type(r), props: properties(r)}}] AS rels
        LIMIT 200
        """
        nodes: dict[str, GraphNode] = {}
        edges: list[GraphEdge] = []
        with driver.session() as session:
            result = session.run(cypher, {"entity_id": entity_id})
            for record in result:
                for n, lns in [(record["n"], record["lns"]), (record["m"], record["lms"])]:
                    nid = n.get("id") or n.get("fingerprint") or n.get("address")
                    if nid and nid not in nodes:
                        nodes[nid] = GraphNode(
                            id=nid,
                            label=str(dict(n))[:60],
                            type=lns[0] if lns else "Unknown",
                            properties=dict(n),
                        )
                for rel in record["rels"]:
                    edges.append(
                        GraphEdge(
                            source=entity_id,
                            target=str(
                                record["m"].get("id") or record["m"].get("fingerprint") or ""
                            ),
                            type=rel["type"],
                            properties=rel["props"],
                        )
                    )
        return GraphResponse(nodes=list(nodes.values()), edges=edges)

    def _subgraph_in_memory(self, entity_id: str, depth: int) -> GraphResponse:
        nodes: dict[str, GraphNode] = {}
        edges: list[GraphEdge] = []
        if entity_id in self._in_memory_fallback:
            nodes[entity_id] = GraphNode(
                id=entity_id,
                label=f"Account {entity_id[:8]}",
                type="Account",
                properties=self._in_memory_fallback[entity_id],
            )
            for e in self._in_memory_fallback[entity_id].get("edges", []):
                edges.append(
                    GraphEdge(
                        source=entity_id,
                        target=e["to"],
                        type="TRANSFERRED_TO",
                        properties={"amount": e["amount"]},
                    )
                )
        return GraphResponse(nodes=list(nodes.values()), edges=edges)

    # ── Graph algorithms (run periodically) ─────────────────────────────

    def detect_mule_rings(self, min_community_size: int = 3) -> list[dict[str, Any]]:
        """Run Louvain community detection; return suspected mule rings."""
        driver = self._ensure_driver()
        if driver is None:
            return []
        cypher = """
        CALL gds.louvain.stream('identity-graph', {relationshipWeightProperty: 'total_amount'})
        YIELD nodeId, communityId
        WITH gds.util.asNode(nodeId) AS n, communityId
        WHERE n:Account
        WITH communityId, collect(n) AS members, count(n) AS size
        WHERE size >= $min_size
        RETURN communityId, size, [m IN members | m.id] AS member_ids
        """
        rings: list[dict[str, Any]] = []
        try:
            with driver.session() as session:
                result = session.run(cypher, {"min_size": min_community_size})
                for record in result:
                    rings.append(
                        {
                            "community_id": record["communityId"],
                            "size": record["size"],
                            "member_account_ids": record["member_ids"],
                        }
                    )
                    # Mark the ring
                    session.run(
                        """
                        MATCH (a:Account) WHERE a.id IN $ids
                        MERGE (r:MuleRing {id: $ring_id})
                        ON CREATE SET r.detected_at = datetime(), r.confidence = 0.7
                        MERGE (a)-[:MEMBER_OF]->(r)
                    """,
                        {"ids": record["member_ids"], "ring_id": f"ring-{record['communityId']}"},
                    )
        except Exception as e:
            logger.warning("Mule ring detection failed: %s", e)
        return rings

    def get_shared_device_count(self, device_fp: str) -> int:
        driver = self._ensure_driver()
        if driver is None:
            return 1
        with driver.session() as session:
            result = session.run(
                """
                MATCH (d:Device {fingerprint: $fp})<-[:USED_ON]-(a:Account)
                RETURN count(DISTINCT a) AS n
            """,
                {"fp": device_fp},
            )
            return int(result.single()["n"])

    def get_shared_ip_count(self, ip: str) -> int:
        driver = self._ensure_driver()
        if driver is None:
            return 1
        with driver.session() as session:
            result = session.run(
                """
                MATCH (i:IP {address: $ip})<-[:FROM_IP]-(p:Person)
                RETURN count(DISTINCT p) AS n
            """,
                {"ip": ip},
            )
            return int(result.single()["n"])


_singleton: GraphClient | None = None


def get_graph_client() -> GraphClient:
    global _singleton
    if _singleton is None:
        _singleton = GraphClient()
    return _singleton
