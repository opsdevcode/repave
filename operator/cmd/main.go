/*
Copyright 2026 repave contributors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
*/

package main

import (
	"crypto/tls"
	"flag"
	"os"
	"time"

	"k8s.io/apimachinery/pkg/runtime"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/healthz"
	"sigs.k8s.io/controller-runtime/pkg/log/zap"
	metricsserver "sigs.k8s.io/controller-runtime/pkg/metrics/server"
	"sigs.k8s.io/controller-runtime/pkg/webhook"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/controller"
	"github.com/opsdevcode/repave/operator/internal/github"
	"github.com/opsdevcode/repave/operator/internal/inventory"
	"github.com/opsdevcode/repave/operator/internal/repave"
)

// remoteResyncFromEnv reads REPAVE_OPERATOR_REMOTE_RESYNC (Go duration, for example 15m).
// Invalid or unset values fall back to the controller default.
func remoteResyncFromEnv() time.Duration {
	raw := os.Getenv("REPAVE_OPERATOR_REMOTE_RESYNC")
	if raw == "" {
		return 0
	}
	parsed, err := time.ParseDuration(raw)
	if err != nil || parsed <= 0 {
		setupLog.Info("ignoring invalid REPAVE_OPERATOR_REMOTE_RESYNC", "value", raw)
		return 0
	}
	return parsed
}

var (
	scheme   = runtime.NewScheme()
	setupLog = ctrl.Log.WithName("setup")
)

func init() {
	utilruntime.Must(clientgoscheme.AddToScheme(scheme))
	utilruntime.Must(repavev1alpha1.AddToScheme(scheme))
	utilruntime.Must(repavev1beta1.AddToScheme(scheme))
}

func main() {
	var metricsAddr string
	var probeAddr string
	var enableLeaderElection bool
	var secureMetrics bool
	flag.StringVar(&metricsAddr, "metrics-bind-address", "0", "The address the metrics endpoint binds to.")
	flag.StringVar(&probeAddr, "health-probe-bind-address", ":8081", "The address the probe endpoint binds to.")
	flag.BoolVar(&enableLeaderElection, "leader-elect", false,
		"Enable leader election for controller manager.")
	flag.BoolVar(&secureMetrics, "metrics-secure", false,
		"If set, the metrics endpoint is served securely.")
	opts := zap.Options{Development: true}
	opts.BindFlags(flag.CommandLine)
	flag.Parse()

	ctrl.SetLogger(zap.New(zap.UseFlagOptions(&opts)))

	mgr, err := ctrl.NewManager(ctrl.GetConfigOrDie(), ctrl.Options{
		Scheme: scheme,
		Metrics: metricsserver.Options{
			BindAddress:   metricsAddr,
			SecureServing: secureMetrics,
			TLSOpts:       []func(*tls.Config){},
		},
		WebhookServer: webhook.NewServer(webhook.Options{
			Port: 9443,
		}),
		HealthProbeBindAddress: probeAddr,
		LeaderElection:         enableLeaderElection,
		LeaderElectionID:       "repave.dev.goldenpathrepo",
	})
	if err != nil {
		setupLog.Error(err, "unable to start manager")
		os.Exit(1)
	}

	githubToken, err := github.ResolveAccessToken("")
	if err != nil {
		setupLog.Error(err, "unable to resolve GitHub access token")
		os.Exit(1)
	}
	var ghClient github.Client
	if githubToken != "" {
		ghClient = &github.HTTPClient{Token: githubToken}
	}

	repaveCfg := repave.ConfigFromEnv(
		os.Getenv("REPAVE_REPO_ROOT"),
		os.Getenv("REPAVE_CLI"),
		os.Getenv("REPAVE_API_URL"),
	)

	if err := (&repavev1alpha1.GoldenPathRepo{}).SetupWebhookWithManager(mgr); err != nil {
		setupLog.Error(err, "unable to create webhook", "webhook", "GoldenPathRepo")
		os.Exit(1)
	}
	if err := (&repavev1alpha1.Blueprint{}).SetupWebhookWithManager(mgr); err != nil {
		setupLog.Error(err, "unable to create webhook", "webhook", "Blueprint")
		os.Exit(1)
	}

	if err := (&controller.GoldenPathRepoReconciler{
		Client: mgr.GetClient(),
		Scheme: mgr.GetScheme(),
		PlanUpgrader:  repave.NewPlanUpgrader(repaveCfg),
		ApplyUpgrader: repave.NewApplyUpgrader(repaveCfg),
		GitHub:        ghClient,
		RepaveConfig:  repaveCfg,
		GitHubToken:   githubToken,
		Fetcher:       inventory.GitFetcher{},
		RemoteResync:  remoteResyncFromEnv(),
	}).SetupWithManager(mgr); err != nil {
		setupLog.Error(err, "unable to create controller", "controller", "GoldenPathRepo")
		os.Exit(1)
	}

	if err := mgr.AddHealthzCheck("healthz", healthz.Ping); err != nil {
		setupLog.Error(err, "unable to set up health check")
		os.Exit(1)
	}
	if err := mgr.AddReadyzCheck("readyz", healthz.Ping); err != nil {
		setupLog.Error(err, "unable to set up ready check")
		os.Exit(1)
	}

	setupLog.Info("starting manager")
	if err := mgr.Start(ctrl.SetupSignalHandler()); err != nil {
		setupLog.Error(err, "problem running manager")
		os.Exit(1)
	}
}
