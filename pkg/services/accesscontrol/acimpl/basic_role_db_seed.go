package acimpl

import (
	"context"
	"errors"
	"time"

	"github.com/grafana/grafana/pkg/infra/serverlock"
	"github.com/grafana/grafana/pkg/services/accesscontrol"
)

const (
	ossBasicRoleSeedLockName = "oss-ac-basic-role-seeder"
	ossBasicRoleSeedTimeout  = 2 * time.Minute
)

// refreshBasicRolePermissionsInDB ensures basic role permissions are fully derived from in-memory registrations
func (s *Service) refreshBasicRolePermissionsInDB(ctx context.Context, rolesSnapshot map[string][]accesscontrol.Permission) error {
	if s.sql == nil || s.seeder == nil {
		return nil
	}

	run := func(ctx context.Context) error {
		desired := map[accesscontrol.SeedPermission]struct{}{}
		for role, permissions := range rolesSnapshot {
			for _, permission := range permissions {
				desired[accesscontrol.SeedPermission{BuiltInRole: role, Action: permission.Action, Scope: permission.Scope}] = struct{}{}
			}
		}
		s.seeder.SetDesiredPermissions(desired)
		return s.seeder.Seed(ctx)
	}

	if s.serverLock == nil {
		return run(ctx)
	}

	var err error
	attempt := func(ctx context.Context) error {
		return s.serverLock.LockExecuteAndRelease(ctx, ossBasicRoleSeedLockName, ossBasicRoleSeedTimeout, func(ctx context.Context) {
			err = run(ctx)
		})
	}
	var errLock error
	if s.cfg != nil && s.cfg.Raw != nil && s.cfg.Raw.Section("database").Key("cockroachdb_manual_bootstrap").MustBool(false) {
		errLock = waitForBasicRoleSeed(ctx, attempt)
	} else {
		errLock = attempt(ctx)
	}
	if errLock != nil {
		return errLock
	}
	return err
}

// Concurrent prototype nodes must wait for permission seeding, rather than skip it or exit.
func waitForBasicRoleSeed(ctx context.Context, attempt func(context.Context) error) error {
	ctx, cancel := context.WithTimeout(ctx, ossBasicRoleSeedTimeout)
	defer cancel()
	for {
		if err := ctx.Err(); err != nil {
			return err
		}
		err := attempt(ctx)
		var held *serverlock.ServerLockExistsError
		if !errors.As(err, &held) {
			return err
		}
		timer := time.NewTimer(100 * time.Millisecond)
		select {
		case <-ctx.Done():
			timer.Stop()
			return ctx.Err()
		case <-timer.C:
		}
	}
}
