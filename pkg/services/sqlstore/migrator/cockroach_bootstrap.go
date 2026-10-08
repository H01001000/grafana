package migrator

import (
	"context"
	"fmt"
	"strings"
)

func (mg *Migrator) verifyCockroachBootstrap(ctx context.Context) error {
	var version string
	session := mg.DBEngine.NewSession().Context(ctx)
	defer session.Close()
	if _, err := session.SQL("SELECT version()").Get(&version); err != nil {
		return fmt.Errorf("verify CockroachDB server: %w", err)
	}
	if !strings.Contains(version, "CockroachDB") {
		return fmt.Errorf("cockroachdb_manual_bootstrap requires a CockroachDB server")
	}
	if _, err := mg.GetMigrationLog(); err != nil {
		return fmt.Errorf("manual CRDB bootstrap required: read %s: %w", mg.tableName, err)
	}
	if err := mg.addObsoleteMigrations(); err != nil {
		return err
	}
	if err := verifyBootstrapMigrations(mg.migrations, mg.logMap, mg.tableName); err != nil {
		return err
	}
	mg.Logger.FromContext(ctx).Info("Verified manual CRDB bootstrap; migrations are read-only", "table", mg.tableName, "required", len(mg.migrations))
	return nil
}

func verifyBootstrapMigrations(migrations []Migration, records map[string]MigrationLog, table string) error {
	for _, m := range migrations {
		if m.SkipMigrationLog() {
			return fmt.Errorf("manual CRDB bootstrap cannot verify unrecorded migration %q", m.Id())
		}
		if record, ok := records[m.Id()]; !ok || !record.Success {
			return fmt.Errorf("manual CRDB bootstrap required: %s is missing successful migration %q; no migrations were executed", table, m.Id())
		}
	}
	return nil
}
