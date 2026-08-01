package fleetsync

import (
	"os"
	"strconv"
	"strings"
	"time"
)

const (
	defaultNamespace = "default"
	defaultInterval  = 5 * time.Minute
	managedByLabel   = "repave.dev/managed-by"
	managedByValue   = "repave-fleet"
)

// Config controls periodic GoldenPathRepo sync from the fleet registry file.
type Config struct {
	Enabled            bool
	RegistryPath       string
	Namespace          string
	Interval           time.Duration
	EnableRemediation  bool
}

// LoadConfigFromEnv reads REPAVE_FLEET_SYNC_* settings.
func LoadConfigFromEnv() Config {
	enabled := strings.EqualFold(os.Getenv("REPAVE_FLEET_SYNC_ENABLED"), "true")
	path := strings.TrimSpace(os.Getenv("REPAVE_FLEET_FILE"))
	if path == "" {
		path = strings.TrimSpace(os.Getenv("REPAVE_FLEET_REGISTRY_PATH"))
	}
	namespace := strings.TrimSpace(os.Getenv("REPAVE_FLEET_GITOPS_NAMESPACE"))
	if namespace == "" {
		namespace = defaultNamespace
	}
	interval := defaultInterval
	if raw := strings.TrimSpace(os.Getenv("REPAVE_FLEET_SYNC_INTERVAL")); raw != "" {
		if seconds, err := strconv.Atoi(raw); err == nil && seconds > 0 {
			interval = time.Duration(seconds) * time.Second
		}
	}
	enableRemediation := strings.EqualFold(os.Getenv("REPAVE_FLEET_ENABLE_REMEDIATION"), "true")
	return Config{
		Enabled:           enabled && path != "",
		RegistryPath:      path,
		Namespace:         namespace,
		Interval:          interval,
		EnableRemediation: enableRemediation,
	}
}
