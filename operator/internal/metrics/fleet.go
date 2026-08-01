package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"sigs.k8s.io/controller-runtime/pkg/metrics"
)

const (
	namespaceLabel = "namespace"
	campaignLabel  = "campaign"
)

var (
	fleetOutOfDateRepos = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "repave_fleet_out_of_date_repos",
			Help: "GoldenPathRepos with pin drift in an upgrade campaign slice.",
		},
		[]string{namespaceLabel, campaignLabel},
	)
	fleetOldestDriftAgeSeconds = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "repave_fleet_oldest_drift_age_seconds",
			Help: "Age in seconds of the longest-running drift in a campaign slice.",
		},
		[]string{namespaceLabel, campaignLabel},
	)
	fleetOpenRemediationPRs = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "repave_fleet_open_remediation_prs",
			Help: "Open remediation pull requests in an upgrade campaign slice.",
		},
		[]string{namespaceLabel, campaignLabel},
	)
	remediationMTTRSeconds = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "repave_remediation_mttr_seconds",
			Help:    "Time from drift detection to pins realigned for a GoldenPathRepo.",
			Buckets: prometheus.ExponentialBuckets(300, 2, 10),
		},
		[]string{namespaceLabel, campaignLabel},
	)
)

func init() {
	metrics.Registry.MustRegister(
		fleetOutOfDateRepos,
		fleetOldestDriftAgeSeconds,
		fleetOpenRemediationPRs,
		remediationMTTRSeconds,
	)
}

// RecordCampaignSnapshot updates gauges for a campaign fleet slice.
func RecordCampaignSnapshot(
	namespace string,
	campaign string,
	outOfDate int32,
	oldestDriftAgeSeconds int64,
	openPRs int32,
) {
	labels := prometheus.Labels{
		namespaceLabel: namespace,
		campaignLabel:  campaign,
	}
	fleetOutOfDateRepos.With(labels).Set(float64(outOfDate))
	fleetOldestDriftAgeSeconds.With(labels).Set(float64(oldestDriftAgeSeconds))
	fleetOpenRemediationPRs.With(labels).Set(float64(openPRs))
}

// RecordRemediationMTTR observes drift-to-ready duration for a repo.
func RecordRemediationMTTR(namespace, campaign string, seconds float64) {
	if seconds <= 0 {
		return
	}
	remediationMTTRSeconds.With(prometheus.Labels{
		namespaceLabel: namespace,
		campaignLabel:  campaign,
	}).Observe(seconds)
}
