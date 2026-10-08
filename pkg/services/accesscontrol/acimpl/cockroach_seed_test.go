package acimpl

import (
	"context"
	"errors"
	"testing"

	"github.com/grafana/grafana/pkg/infra/serverlock"
	"github.com/stretchr/testify/require"
)

func TestCockroachRoleSeedWaitsForOtherNode(t *testing.T) {
	attempts := 0
	err := waitForBasicRoleSeed(context.Background(), func(context.Context) error {
		attempts++
		if attempts < 3 {
			return &serverlock.ServerLockExistsError{}
		}
		return nil
	})
	require.NoError(t, err)
	require.Equal(t, 3, attempts)
}

func TestCockroachRoleSeedPropagatesFailureAndCancellation(t *testing.T) {
	failure := errors.New("seeding failed")
	err := waitForBasicRoleSeed(context.Background(), func(context.Context) error { return failure })
	require.ErrorIs(t, err, failure)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	err = waitForBasicRoleSeed(ctx, func(context.Context) error { t.Fatal("cancelled seed attempted"); return nil })
	require.ErrorIs(t, err, context.Canceled)
}
