package crdb

import (
	"context"
	"database/sql"
	"os"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	_ "github.com/lib/pq"
	"github.com/stretchr/testify/require"
)

func TestCockroachTransactionRetryIntegration(t *testing.T) {
	dsn := os.Getenv("GRAFANA_CRDB_TEST_DSN")
	if dsn == "" {
		t.Skip("requires a disposable CRDB test database")
	}
	database, err := sql.Open("postgres", dsn)
	require.NoError(t, err)
	defer database.Close()
	database.SetMaxOpenConns(4)
	_, err = database.Exec("CREATE TABLE prototype_retry_counter(id INT PRIMARY KEY, value INT NOT NULL)")
	require.NoError(t, err)
	defer database.Exec("DROP TABLE prototype_retry_counter")
	_, err = database.Exec("INSERT INTO prototype_retry_counter VALUES (1,0)")
	require.NoError(t, err)
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	var retries atomic.Int64
	errors := make(chan error, 4)
	var workers sync.WaitGroup
	for range 4 {
		workers.Add(1)
		go func() {
			defer workers.Done()
			for range 10 {
				err := Retry(ctx, 50, func() error {
					tx, err := database.BeginTx(ctx, nil)
					if err != nil {
						return err
					}
					defer tx.Rollback()
					var value int
					if err = tx.QueryRowContext(ctx, "SELECT value FROM prototype_retry_counter WHERE id=1").Scan(&value); err != nil {
						return err
					}
					time.Sleep(time.Millisecond)
					_, err = tx.ExecContext(ctx, "UPDATE prototype_retry_counter SET value=$1 WHERE id=1", value+1)
					if err == nil {
						err = tx.Commit()
					}
					if IsRetryable(err) {
						retries.Add(1)
					}
					return err
				})
				if err != nil {
					errors <- err
					return
				}
			}
		}()
	}
	workers.Wait()
	close(errors)
	for err := range errors {
		require.NoError(t, err)
	}
	var final int
	require.NoError(t, database.QueryRow("SELECT value FROM prototype_retry_counter WHERE id=1").Scan(&final))
	require.Equal(t, 40, final)
	require.Positive(t, retries.Load())
	t.Logf("40 committed increments, %d serialization failures retried", retries.Load())
}
