package dbimpl

import (
	"context"
	"database/sql"
	"testing"

	"github.com/grafana/grafana/pkg/storage/unified/sql/db"
	"github.com/lib/pq"
	"github.com/stretchr/testify/require"
)

type commitFailureDB struct {
	db.DB
	attempts int
}

func (d *commitFailureDB) WithTx(ctx context.Context, opts *sql.TxOptions, f db.TxFunc) error {
	d.attempts++
	if err := f(ctx, nil); err != nil {
		return err
	}
	if d.attempts == 1 {
		return &pq.Error{Code: "40001"}
	}
	return nil
}

func TestCockroachRetriesCommitFailureWithFreshTransaction(t *testing.T) {
	underlying := &commitFailureDB{}
	wrapped := withCockroachRetries(underlying, 2)
	callbacks := 0
	err := wrapped.WithTx(context.Background(), nil, func(context.Context, db.Tx) error {
		callbacks++
		return nil
	})
	require.NoError(t, err)
	require.Equal(t, 2, underlying.attempts)
	require.Equal(t, 2, callbacks)
}
