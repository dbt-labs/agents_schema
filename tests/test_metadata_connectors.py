import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents_schema import metadata_connectors


class FakeDestination:
    def __init__(self):
        self.calls = []

    def upsert_rows(self, table, rows):
        self.calls.append(("upsert", table.name, list(rows)))

    def replace_table(self, table):
        self.calls.append(("replace", table.name))

    def insert_rows(self, table, rows):
        self.calls.append(("insert", table.name, list(rows)))


class DestinationContext:
    def __init__(self, dest):
        self.dest = dest

    def __enter__(self):
        return self.dest

    def __exit__(self, exc_type, exc, tb):
        return None


FIXTURES = {
    "powerbi": {
        "workspaces": [
            {
                "id": "workspace-1",
                "name": "Finance",
                "datasets": [
                    {
                        "id": "model-1",
                        "name": "Finance Model",
                        "tables": [
                            {
                                "name": "Revenue",
                                "columns": [{"name": "amount", "dataType": "decimal"}],
                                "measures": [{"name": "MRR", "expression": "SUM(Revenue[amount])"}],
                            }
                        ],
                    }
                ],
                "reports": [{"id": "report-1", "name": "Executive MRR", "datasetId": "model-1"}],
            }
        ]
    },
    "tableau": {
        "data": {
            "workbooks": [
                {
                    "id": "workbook-1",
                    "name": "Executive Dashboard",
                    "owner": {"name": "analyst"},
                    "upstreamDatasources": [{"id": "datasource-1"}],
                    "dashboards": [{"id": "dashboard-1", "name": "Revenue"}],
                }
            ],
            "datasources": [
                {
                    "id": "datasource-1",
                    "name": "Revenue Datasource",
                    "fields": [{"id": "field-1", "name": "amount", "dataType": "number"}],
                }
            ],
        }
    },
    "dbt_semantic": {
        "semantic_models": [
            {
                "name": "orders",
                "model": "ref('fct_orders')",
                "entities": [{"name": "order", "type": "primary", "expr": "order_id"}],
                "dimensions": [{"name": "ordered_at", "type": "time", "expr": "ordered_at"}],
                "measures": [{"name": "order_total", "agg": "sum", "expr": "amount"}],
            }
        ],
        "metrics": [{"name": "revenue", "type": "simple", "type_params": {"measure": "order_total"}}],
    },
    "datahub": {
        "searchResults": [
            {
                "entity": {
                    "urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.orders,PROD)",
                    "type": "dataset",
                    "platform": {"name": "snowflake"},
                    "properties": {"name": "orders", "description": "Curated orders."},
                    "schemaMetadata": {"fields": [{"fieldPath": "order_id", "nativeDataType": "VARCHAR"}]},
                    "ownership": {"owners": [{"owner": "urn:li:corpuser:ana", "type": "DATAOWNER"}]},
                    "upstreamLineage": {"upstreams": [{"dataset": "urn:li:dataset:raw.orders"}]},
                }
            }
        ]
    },
    "openmetadata": {
        "data": [
            {
                "fullyQualifiedName": "snowflake.analytics.orders",
                "entityType": "table",
                "name": "orders",
                "columns": [{"name": "order_id", "dataType": "VARCHAR"}],
                "lineage": {"upstreamEdges": [{"fromFqn": "snowflake.raw.orders"}]},
            }
        ]
    },
    "atlan": {
        "entities": [
            {
                "guid": "asset-1",
                "typeName": "Table",
                "attributes": {
                    "qualifiedName": "snowflake/analytics/orders",
                    "name": "orders",
                    "ownerUsers": ["ana"],
                },
                "relationshipAttributes": {
                    "columns": [
                        {
                            "guid": "field-1",
                            "attributes": {
                                "qualifiedName": "snowflake/analytics/orders/order_id",
                                "name": "order_id",
                                "dataType": "VARCHAR",
                            },
                        }
                    ]
                },
                "lineage": [{"upstreamGuid": "raw-1", "downstreamGuid": "asset-1"}],
            }
        ]
    },
    "alation": {
        "data_sources": [{"id": 1, "title": "Snowflake", "dbtype": "snowflake"}],
        "tables": [
            {
                "id": 10,
                "ds_id": 1,
                "schema_name": "analytics",
                "name": "orders",
                "columns": [{"id": 100, "name": "order_id", "data_type": "VARCHAR"}],
            }
        ],
        "glossary_terms": [{"id": 20, "title": "Revenue", "description": "Booked revenue."}],
    },
    "collibra": {
        "assets": [
            {
                "id": "asset-1",
                "name": "orders",
                "type": {"name": "Table"},
                "attributes": [{"type": {"name": "Description"}, "value": "Curated orders."}],
                "relations": [{"targetId": "asset-2", "type": "Table contains Column"}],
                "responsibilities": [{"ownerId": "user-1", "role": "Steward"}],
            }
        ]
    },
    "metabase": {
        "databases": [
            {
                "id": 1,
                "name": "Warehouse",
                "engine": "snowflake",
                "tables": [
                    {
                        "id": 10,
                        "schema": "analytics",
                        "name": "orders",
                        "fields": [{"id": 100, "name": "order_id", "base_type": "type/Text"}],
                    }
                ],
            }
        ],
        "cards": [{"id": 50, "name": "Revenue", "database_id": 1, "dataset_query": {"database": 1}}],
        "dashboards": [{"id": 60, "name": "Executive"}],
    },
    "cube": {
        "cubes": [
            {
                "name": "Orders",
                "title": "Orders",
                "measures": [{"name": "count", "type": "count"}],
                "dimensions": [{"name": "status", "type": "string", "sql": "status"}],
                "segments": [{"name": "completed", "sql": "${CUBE}.status = 'completed'"}],
                "joins": {"Users": {"relationship": "many_to_one", "sql": "${CUBE}.user_id = ${Users}.id"}},
            }
        ]
    },
}


class MetadataConnectorTests(unittest.TestCase):
    def test_each_new_connector_writes_root_and_source_rows(self):
        for provider, fixture in FIXTURES.items():
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"{provider}.json"
                path.write_text(json.dumps(fixture))
                dest = FakeDestination()

                with (
                    patch("agents_schema.metadata_helpers.open_destination", return_value=DestinationContext(dest)),
                    patch("builtins.print"),
                ):
                    metadata_connectors.run(provider, {"metadata_connection": {"path": str(path)}})

                self.assertEqual(dest.calls[0][0], "upsert")
                self.assertEqual({row[0] for row in dest.calls[0][2]}, {provider})
                self.assertTrue(any(call[0] == "replace" for call in dest.calls))
                inserted = [call for call in dest.calls if call[0] == "insert"]
                self.assertTrue(inserted)
                self.assertTrue(any(call[2] for call in inserted))


if __name__ == "__main__":
    unittest.main()
