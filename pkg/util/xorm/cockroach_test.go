package xorm

import (
	"os"
	"testing"
	"time"

	_ "github.com/lib/pq"
	"github.com/stretchr/testify/require"
)

type cockroachLimitedRow struct {
	ID        int64  `xorm:"'id' pk"`
	Group     string `xorm:"grp"`
	Value     int64
	DeletedAt time.Time `xorm:"deleted"`
}

func TestCockroachLimitedWritesIntegration(t *testing.T) {
	dsn := os.Getenv("GRAFANA_CRDB_TEST_DSN")
	if dsn == "" {
		t.Skip("requires a disposable CRDB test database")
	}
	engine, err := NewEngine("postgres", dsn)
	require.NoError(t, err)
	defer engine.Close()
	engine.EnableCockroachDB()
	_, err = engine.Exec("CREATE TABLE prototype_limited_writes (id INT PRIMARY KEY, grp STRING, value INT, deleted_at TIMESTAMP NULL)")
	require.NoError(t, err)
	defer engine.Exec("DROP TABLE prototype_limited_writes")
	_, err = engine.Exec("INSERT INTO prototype_limited_writes(id,grp,value) VALUES (1,'target',10),(2,'other',20),(3,'target',30)")
	require.NoError(t, err)
	rows, err := engine.Table("prototype_limited_writes").Where("grp = ?", "target").Desc("id").Limit(1).Cols("value").Update(&cockroachLimitedRow{Value: 99})
	require.NoError(t, err)
	require.Equal(t, int64(1), rows)
	var selected cockroachLimitedRow
	_, err = engine.Table("prototype_limited_writes").ID(3).Get(&selected)
	require.NoError(t, err)
	require.Equal(t, int64(99), selected.Value)
	rows, err = engine.Table("prototype_limited_writes").Where("grp = ?", "target").Asc("id").Limit(1).Delete(&cockroachLimitedRow{})
	require.NoError(t, err)
	require.Equal(t, int64(1), rows)
	var all []cockroachLimitedRow
	err = engine.Table("prototype_limited_writes").Unscoped().Asc("id").Find(&all)
	require.NoError(t, err)
	require.Len(t, all, 3)
	require.False(t, all[0].DeletedAt.IsZero())
	require.True(t, all[1].DeletedAt.IsZero())
	require.True(t, all[2].DeletedAt.IsZero())
	rows, err = engine.Table("prototype_limited_writes").Unscoped().Where("grp = ?", "target").Desc("id").Limit(1).Delete(&cockroachLimitedRow{})
	require.NoError(t, err)
	require.Equal(t, int64(1), rows)
	rows, err = engine.Table("prototype_limited_writes").Where("grp = ?", "other").Desc("id").Limit(1).Update(&map[string]any{"value": 77})
	require.NoError(t, err)
	require.Equal(t, int64(1), rows)
	selected = cockroachLimitedRow{}
	_, err = engine.Table("prototype_limited_writes").ID(2).Get(&selected)
	require.NoError(t, err)
	require.Equal(t, int64(77), selected.Value)
}
