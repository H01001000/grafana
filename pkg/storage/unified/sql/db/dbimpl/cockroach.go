package dbimpl

import (
	"context"
	"database/sql"

	"github.com/grafana/grafana/pkg/storage/unified/sql/db"
	"github.com/grafana/grafana/pkg/util/crdb"
)

type cockroachRetryDB struct {
	db.DB
	retries int
}

func withCockroachRetries(d db.DB, retries int) db.DB {
	return cockroachRetryDB{DB: d, retries: retries}
}

func (d cockroachRetryDB) WithTx(ctx context.Context, opts *sql.TxOptions, f db.TxFunc) error {
	return crdb.Retry(ctx, d.retries, func() error {
		return d.DB.WithTx(ctx, opts, f)
	})
}
