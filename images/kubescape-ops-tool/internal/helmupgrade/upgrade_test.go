package helmupgrade

import (
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"

	"helm.sh/helm/v3/pkg/action"
	"helm.sh/helm/v3/pkg/chart"
	"helm.sh/helm/v3/pkg/chartutil"
	"helm.sh/helm/v3/pkg/cli"
	kubefake "helm.sh/helm/v3/pkg/kube/fake"
	"helm.sh/helm/v3/pkg/release"
	"helm.sh/helm/v3/pkg/repo"
	"helm.sh/helm/v3/pkg/storage"
	"helm.sh/helm/v3/pkg/storage/driver"
	"sigs.k8s.io/yaml"
)

func TestParseFlagsPrefersFlagsOverEnv(t *testing.T) {
	env := map[string]string{
		EnvRelease:      "env-release",
		EnvNamespace:    "env-ns",
		EnvChartRepo:    "env-repo",
		EnvChartRepoURL: "https://env.example/charts",
		EnvChartName:    "env-chart",
		EnvVersion:      "9.9.9",
	}
	getenv := func(k string) string { return env[k] }

	o, err := ParseFlags([]string{"--release", "flag-release", "--chart-name", "flag-chart"}, getenv, io.Discard)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if o.Release != "flag-release" || o.ChartName != "flag-chart" {
		t.Fatalf("flags did not win: %+v", o)
	}
	if o.Namespace != "env-ns" || o.ChartRepo != "env-repo" ||
		o.ChartRepoURL != "https://env.example/charts" || o.Version != "9.9.9" {
		t.Fatalf("env fallback not applied: %+v", o)
	}
}

func TestParseFlagsHasNoBakedInDefaults(t *testing.T) {
	noEnv := func(string) string { return "" }
	for _, args := range [][]string{
		{},
		{"--release", "r"},
		{"--release", "r", "--namespace", "n"},
		{"--release", "r", "--namespace", "n", "--chart-repo", "repo"},
		{"--release", "r", "--namespace", "n", "--chart-repo", "repo", "--chart-repo-url", "https://x"},
	} {
		if _, err := ParseFlags(args, noEnv, io.Discard); err == nil {
			t.Fatalf("args %v must be rejected: nothing may be defaulted in Go", args)
		}
	}

	o, err := ParseFlags([]string{
		"--release", "r", "--namespace", "n", "--chart-repo", "repo",
		"--chart-repo-url", "https://x", "--chart-name", "c",
	}, noEnv, io.Discard)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if o.Version != "" {
		t.Fatalf("--version must stay empty, got %q", o.Version)
	}
}

// chartRepoServer serves a real Helm repository (index.yaml + packaged chart)
// so the SDK's index resolution is exercised without network access.
func chartRepoServer(t *testing.T, ch *chart.Chart) string {
	t.Helper()
	dir := t.TempDir()
	if _, err := chartutil.Save(ch, dir); err != nil {
		t.Fatalf("package chart: %v", err)
	}
	srv := httptest.NewServer(http.FileServer(http.Dir(dir)))
	t.Cleanup(srv.Close)

	index, err := repo.IndexDirectory(dir, srv.URL)
	if err != nil {
		t.Fatalf("index directory: %v", err)
	}
	index.SortEntries()
	if err := index.WriteFile(filepath.Join(dir, "index.yaml"), 0o644); err != nil {
		t.Fatalf("write index: %v", err)
	}
	return srv.URL
}

func testChart(version string) *chart.Chart {
	return &chart.Chart{
		Metadata: &chart.Metadata{APIVersion: chart.APIVersionV2, Name: "demo", Version: version},
		Templates: []*chart.File{{
			Name: "templates/cm.yaml",
			Data: []byte("apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: demo\n"),
		}},
	}
}

// testChartWithValues builds a chart whose ConfigMap renders two values keys,
// so a test can tell whether the chart's own Values.yaml defaults survived an
// upgrade alongside a previously-supplied user override for a different key.
//
// chartutil.Save only serializes values.yaml from Chart.Raw (not the Values
// field directly), so Raw must carry the same content for it to survive the
// package/serve/load round trip chartRepoServer performs.
func testChartWithValues(t *testing.T, version string, values map[string]interface{}) *chart.Chart {
	t.Helper()
	rawValues, err := yaml.Marshal(values)
	if err != nil {
		t.Fatalf("marshal values: %v", err)
	}
	return &chart.Chart{
		Metadata: &chart.Metadata{APIVersion: chart.APIVersionV2, Name: "demo", Version: version},
		Values:   values,
		Raw:      []*chart.File{{Name: "values.yaml", Data: rawValues}},
		Templates: []*chart.File{{
			Name: "templates/cm.yaml",
			Data: []byte("apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: demo\ndata:\n" +
				"  existingKey: {{ .Values.existingKey | quote }}\n" +
				"  newKey: {{ .Values.newKey | default \"MISSING\" | quote }}\n"),
		}},
	}
}

func testSettings(t *testing.T, namespace string) *cli.EnvSettings {
	t.Helper()
	home := t.TempDir()
	settings := cli.New()
	settings.RepositoryConfig = filepath.Join(home, "repositories.yaml")
	settings.RepositoryCache = filepath.Join(home, "cache")
	settings.SetNamespace(namespace)
	return settings
}

func TestAddRepoResolvesIndexFromURL(t *testing.T) {
	url := chartRepoServer(t, testChart("1.0.0"))
	settings := testSettings(t, "kubescape")

	index, err := AddRepo(settings, "kubescape", url)
	if err != nil {
		t.Fatalf("AddRepo: %v", err)
	}
	if _, err := index.Get("demo", "1.0.0"); err != nil {
		t.Fatalf("chart not found in resolved index: %v", err)
	}

	repoFile, err := repo.LoadFile(settings.RepositoryConfig)
	if err != nil {
		t.Fatalf("load repositories file: %v", err)
	}
	entry := repoFile.Get("kubescape")
	if entry == nil || entry.URL != url {
		t.Fatalf("repo entry not persisted: %+v", entry)
	}
}

func TestAddRepoFailsOnUnreachableURL(t *testing.T) {
	settings := testSettings(t, "kubescape")
	if _, err := AddRepo(settings, "kubescape", "http://127.0.0.1:1/charts"); err == nil {
		t.Fatal("expected an error for an unreachable repo URL")
	}
}

func TestUpgradeRunsAgainstInMemoryStorage(t *testing.T) {
	installed := testChart("1.0.0")
	url := chartRepoServer(t, testChart("2.0.0"))
	settings := testSettings(t, "kubescape")

	cfg := &action.Configuration{
		Releases:     storage.Init(driver.NewMemory()),
		KubeClient:   &kubefake.FailingKubeClient{PrintingKubeClient: kubefake.PrintingKubeClient{Out: io.Discard}},
		Capabilities: chartutil.DefaultCapabilities,
		Log:          func(string, ...interface{}) {},
	}
	if err := cfg.Releases.Create(&release.Release{
		Name:      "kubescape",
		Namespace: "kubescape",
		Version:   1,
		Info:      &release.Info{Status: release.StatusDeployed},
		Chart:     installed,
		Config:    map[string]interface{}{},
	}); err != nil {
		t.Fatalf("seed release: %v", err)
	}

	rel, err := Upgrade(cfg, settings, Options{
		Release:      "kubescape",
		Namespace:    "kubescape",
		ChartRepo:    "kubescape",
		ChartRepoURL: url,
		ChartName:    "demo",
	})
	if err != nil {
		t.Fatalf("Upgrade: %v", err)
	}
	if rel.Version != 2 {
		t.Fatalf("revision = %d, want 2", rel.Version)
	}
	if rel.Chart.Metadata.Version != "2.0.0" {
		t.Fatalf("upgraded to chart version %s, want 2.0.0", rel.Chart.Metadata.Version)
	}
}

// TestUpgradeKeepsUserValuesAndPicksUpNewChartDefaults guards against
// regressing to action.Upgrade's plain ReuseValues, which would replace the
// target chart's defaults with only the previously installed chart's
// coalesced values -- silently dropping any values key introduced by a newer
// chart version (such as this PR's own kubescapeOpsTool tree) unless the
// user had already set it explicitly.
func TestUpgradeKeepsUserValuesAndPicksUpNewChartDefaults(t *testing.T) {
	installed := testChartWithValues(t, "1.0.0", map[string]interface{}{"existingKey": "old-default"})
	url := chartRepoServer(t, testChartWithValues(t, "2.0.0", map[string]interface{}{
		"existingKey": "new-default",
		"newKey":      "new-default-value",
	}))
	settings := testSettings(t, "kubescape")

	cfg := &action.Configuration{
		Releases:     storage.Init(driver.NewMemory()),
		KubeClient:   &kubefake.FailingKubeClient{PrintingKubeClient: kubefake.PrintingKubeClient{Out: io.Discard}},
		Capabilities: chartutil.DefaultCapabilities,
		Log:          func(string, ...interface{}) {},
	}
	if err := cfg.Releases.Create(&release.Release{
		Name:      "kubescape",
		Namespace: "kubescape",
		Version:   1,
		Info:      &release.Info{Status: release.StatusDeployed},
		Chart:     installed,
		// Models a user who previously ran `--set existingKey=user-override`;
		// they never set newKey because it didn't exist in the old chart.
		Config: map[string]interface{}{"existingKey": "user-override"},
	}); err != nil {
		t.Fatalf("seed release: %v", err)
	}

	rel, err := Upgrade(cfg, settings, Options{
		Release:      "kubescape",
		Namespace:    "kubescape",
		ChartRepo:    "kubescape",
		ChartRepoURL: url,
		ChartName:    "demo",
	})
	if err != nil {
		t.Fatalf("Upgrade: %v", err)
	}
	if !strings.Contains(rel.Manifest, `existingKey: "user-override"`) {
		t.Fatalf("user's previous override was dropped, manifest:\n%s", rel.Manifest)
	}
	if !strings.Contains(rel.Manifest, `newKey: "new-default-value"`) {
		t.Fatalf("new chart default was not applied (ReuseValues regression?), manifest:\n%s", rel.Manifest)
	}
}

func TestUpgradeFailsOnUnknownRelease(t *testing.T) {
	url := chartRepoServer(t, testChart("1.0.0"))
	settings := testSettings(t, "kubescape")
	cfg := &action.Configuration{
		Releases:     storage.Init(driver.NewMemory()),
		KubeClient:   &kubefake.FailingKubeClient{PrintingKubeClient: kubefake.PrintingKubeClient{Out: io.Discard}},
		Capabilities: chartutil.DefaultCapabilities,
		Log:          func(string, ...interface{}) {},
	}

	if _, err := Upgrade(cfg, settings, Options{
		Release:      "absent",
		Namespace:    "kubescape",
		ChartRepo:    "kubescape",
		ChartRepoURL: url,
		ChartName:    "demo",
	}); err == nil {
		t.Fatal("expected an error upgrading a release that does not exist")
	}
}
