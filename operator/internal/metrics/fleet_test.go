package metrics_test

import (
	"testing"

	fleetmetrics "github.com/opsdevcode/repave/operator/internal/metrics"
)

func TestRecordCampaignSnapshotDoesNotPanic(t *testing.T) {
	t.Parallel()
	fleetmetrics.RecordCampaignSnapshot("default", "fleet", 2, 120, 1)
}

func TestRecordRemediationMTTRSkipsNonPositive(t *testing.T) {
	t.Parallel()
	fleetmetrics.RecordRemediationMTTR("default", "fleet", 0)
	fleetmetrics.RecordRemediationMTTR("default", "fleet", -5)
}

func TestRecordRemediationMTTRObservesPositive(t *testing.T) {
	t.Parallel()
	fleetmetrics.RecordRemediationMTTR("default", "fleet", 900)
}
