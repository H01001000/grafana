# CRDB prototype, pinned to Grafana OSS 13.2.3

This experimental backend build uses CockroachDB 26.3.2 as Grafana's internal database and runs two Grafana instances. The frontend and plugins come from the exact upstream 13.2.3 image. It requires a manual schema/data bootstrap from the same stock PostgreSQL-backed Grafana release.

## Build and start

From the repository root:

```sh
docker build -f contrib/crdb-prototype/Dockerfile -t grafana-crdb-prototype:13.2.3 .
python contrib/crdb-prototype/bootstrap.py
```

Requirements: Docker Desktop's desktop-linux context, Python 3 standard library, and available localhost ports 13400–13402. The helper uses a fresh private Compose project. It refuses an existing target schema and requires both runtime instances to be stopped before bootstrap. `--prepare-only` prepares and verifies the schema without starting the runtime instances.

- Grafana A: http://127.0.0.1:13401
- Grafana B: http://127.0.0.1:13402
- Fixture login: admin / disposable-test-only

The database is insecure only inside the private local network and publishes no database ports. Both Grafana nodes share their database and security secret. Their Alertmanager gossip peers use the private network.

## Prototype behavior

`[database] cockroachdb_manual_bootstrap = true` enables the explicit CRDB runtime path while keeping `type = postgres` for the wire driver. `skip_migrations` must stay false.

Each registered migrator checks the server and its successful migration records and returns without executing migrations or acquiring PostgreSQL advisory locks. A missing table, missing successful migration, unsupported unrecorded migration, or wrong server prevents startup. This is how concurrent startup remains read-only: the prototype never attempts a live schema upgrade on CRDB.

The SQL generator uses CRDB's native ordered/limited writes instead of PostgreSQL CTID. Whole-transaction retries handle SQLSTATE 40001 in legacy and unified-storage callback transaction paths, including commit errors. Ambiguous outcomes and unrelated failures are not blindly replayed. Direct streaming/bulk transaction APIs have no automatic replay added; those require their own resumability design before broader support can be claimed.

The helper transfers all actual PostgreSQL migration records and encryption metadata. It translates dump session/ownership metadata and explicit PostgreSQL C collation. Primary keys are declared inline on the empty target, and independent table indexes are created in parallel; the final table counts, source index names, and migration record contents are verified before runtime startup.

## Checks

The baseline runtime suite is `test_runtime.py`. Set `GRAFANA_TEST_PORT=13402` to run read/persistence checks through node B using the same saved session cookie. Additional multi-instance acceptance checks and their results accompany this prototype.

Backend tests:

```sh
go test -short ./pkg/util/crdb ./pkg/util/xorm ./pkg/services/sqlstore/migrator ./pkg/services/sqlstore ./pkg/storage/unified/sql/db/dbimpl
# Run only against a disposable target:
GRAFANA_CRDB_TEST_DSN='host=crdb port=26257 user=grafana dbname=grafana sslmode=disable' \
  go test -run 'TestCockroach.*Integration' -v ./pkg/util/crdb ./pkg/util/xorm
```

## Upgrades and teardown

This is one pinned release. Do not start a different Grafana release against this database and expect automatic migration. A future release requires stopping all writers and a separately validated manual migration/transfer procedure that preserves existing state. Rebootstrapping an empty database is not an upgrade procedure for real data.

Remove only the disposable prototype environment:

```sh
docker --context desktop-linux compose -f contrib/crdb-prototype/compose.yaml down --volumes --remove-orphans
```

The helper does not create a production deployment, publish Docker images, add a load balancer, or prove network-partition/multi-region safety. SQL storage sharing and Alertmanager peer configuration alone do not cluster every Grafana subsystem, such as Grafana Live streaming.
