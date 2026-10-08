package migrator

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestCockroachBootstrapRequiresEverySuccessfulMigration(t *testing.T) {
	first := NewRawSQLMigration("CREATE TABLE first(id INT)")
	first.SetId("first")
	second := NewRawSQLMigration("ALTER TABLE first ADD value INT")
	second.SetId("second")
	for _, tt := range []struct {
		name string
		logs map[string]MigrationLog
		ok   bool
	}{
		{"empty", nil, false},
		{"older release", map[string]MigrationLog{"first": {Success: true}}, false},
		{"failed record", map[string]MigrationLog{"first": {Success: true}, "second": {Success: false}}, false},
		{"matching release", map[string]MigrationLog{"first": {Success: true}, "second": {Success: true}}, true},
	} {
		t.Run(tt.name, func(t *testing.T) {
			err := verifyBootstrapMigrations([]Migration{first, second}, tt.logs, "migration_log")
			if tt.ok {
				require.NoError(t, err)
			} else {
				require.Error(t, err)
			}
		})
	}
}
