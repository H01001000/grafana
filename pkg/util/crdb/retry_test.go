package crdb

import (
	"context"
	"fmt"
	"testing"

	"github.com/lib/pq"
	"github.com/stretchr/testify/require"
)

func TestRetrySerializationAndAmbiguousOutcome(t *testing.T) {
	for _, code := range []string{"40001", "40003", "23505"} {
		t.Run(code, func(t *testing.T) {
			calls := 0
			err := Retry(context.Background(), 2, func() error {
				calls++
				if calls == 1 {
					return fmt.Errorf("commit: %w", &pq.Error{Code: pq.ErrorCode(code)})
				}
				return nil
			})
			if code == "40001" {
				require.NoError(t, err)
				require.Equal(t, 2, calls)
			} else {
				require.Error(t, err)
				require.Equal(t, 1, calls)
			}
		})
	}
}

func TestRetryBoundAndCancellation(t *testing.T) {
	calls := 0
	err := Retry(context.Background(), 1, func() error {
		calls++
		return &pq.Error{Code: "40001"}
	})
	require.Error(t, err)
	require.Equal(t, 2, calls)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	err = Retry(ctx, 10, func() error { t.Fatal("cancelled attempt executed"); return nil })
	require.ErrorIs(t, err, context.Canceled)
}
