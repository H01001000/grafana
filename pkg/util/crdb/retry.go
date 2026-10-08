package crdb

import (
	"context"
	"errors"
	"math/rand/v2"
	"time"
)

// IsRetryable excludes ambiguous outcomes: only an aborted serialization failure can be replayed.
func IsRetryable(err error) bool {
	var state interface{ SQLState() string }
	return errors.As(err, &state) && state.SQLState() == "40001"
}

// Retry replays a whole transaction; attempt must acquire and close a fresh transaction each time.
func Retry(ctx context.Context, retries int, attempt func() error) error {
	for n := 0; ; n++ {
		if err := ctx.Err(); err != nil {
			return err
		}
		err := attempt()
		if !IsRetryable(err) || n >= retries {
			return err
		}
		delay := rand.N(min(25*time.Millisecond<<min(n, 6), time.Second))
		timer := time.NewTimer(delay)
		select {
		case <-ctx.Done():
			timer.Stop()
			return ctx.Err()
		case <-timer.C:
		}
	}
}
