package helmupgrade

import (
	"flag"
	"fmt"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"time"

	"helm.sh/helm/v3/pkg/action"
	"helm.sh/helm/v3/pkg/chart/loader"
	"helm.sh/helm/v3/pkg/cli"
	"helm.sh/helm/v3/pkg/getter"
	"helm.sh/helm/v3/pkg/release"
	"helm.sh/helm/v3/pkg/repo"
)

// Options carries the fully resolved upgrade target. Nothing here has a
// baked-in default: every field comes from a flag or an environment variable.
type Options struct {
	Release      string
	Namespace    string
	ChartRepo    string
	ChartRepoURL string
	ChartName    string
	Version      string
	Timeout      time.Duration
}

const (
	EnvRelease      = "KUBESCAPE_OPS_RELEASE"
	EnvNamespace    = "KUBESCAPE_OPS_NAMESPACE"
	EnvChartRepo    = "KUBESCAPE_OPS_CHART_REPO"
	EnvChartRepoURL = "KUBESCAPE_OPS_CHART_REPO_URL"
	EnvChartName    = "KUBESCAPE_OPS_CHART_NAME"
	EnvVersion      = "KUBESCAPE_OPS_CHART_VERSION"
)

const usage = `Usage: kubescape-ops-tool helm-upgrade [flags]
      --release         Helm release name (required, env KUBESCAPE_OPS_RELEASE)
      --namespace       Release namespace (required, env KUBESCAPE_OPS_NAMESPACE)
      --chart-repo      Local Helm repo name (required, env KUBESCAPE_OPS_CHART_REPO)
      --chart-repo-url  Helm repo index URL (required, env KUBESCAPE_OPS_CHART_REPO_URL)
      --chart-name      Chart name inside the repo (required, env KUBESCAPE_OPS_CHART_NAME)
      --version         Chart version, empty means latest (env KUBESCAPE_OPS_CHART_VERSION)
      --timeout         Upgrade timeout (default: 10m)
`

// ParseFlags resolves options with flag > environment precedence.
func ParseFlags(args []string, getenv func(string) string, errOut io.Writer) (Options, error) {
	var o Options
	fs := flag.NewFlagSet("helm-upgrade", flag.ContinueOnError)
	fs.SetOutput(errOut)
	fs.Usage = func() { fmt.Fprint(errOut, usage) }
	fs.StringVar(&o.Release, "release", "", "Helm release name")
	fs.StringVar(&o.Namespace, "namespace", "", "Release namespace")
	fs.StringVar(&o.Namespace, "n", "", "Release namespace")
	fs.StringVar(&o.ChartRepo, "chart-repo", "", "Local Helm repo name")
	fs.StringVar(&o.ChartRepoURL, "chart-repo-url", "", "Helm repo index URL")
	fs.StringVar(&o.ChartName, "chart-name", "", "Chart name inside the repo")
	fs.StringVar(&o.Version, "version", "", "Chart version, empty means latest")
	fs.DurationVar(&o.Timeout, "timeout", 10*time.Minute, "Upgrade timeout")
	if err := fs.Parse(args); err != nil {
		return o, err
	}

	for _, f := range []struct {
		target *string
		env    string
	}{
		{&o.Release, EnvRelease},
		{&o.Namespace, EnvNamespace},
		{&o.ChartRepo, EnvChartRepo},
		{&o.ChartRepoURL, EnvChartRepoURL},
		{&o.ChartName, EnvChartName},
		{&o.Version, EnvVersion},
	} {
		if *f.target == "" {
			*f.target = getenv(f.env)
		}
	}

	for _, req := range []struct{ val, name string }{
		{o.Release, "--release"},
		{o.Namespace, "--namespace"},
		{o.ChartRepo, "--chart-repo"},
		{o.ChartRepoURL, "--chart-repo-url"},
		{o.ChartName, "--chart-name"},
	} {
		if req.val == "" {
			fmt.Fprint(errOut, usage)
			return o, fmt.Errorf("%s required", req.name)
		}
	}
	return o, nil
}

// AddRepo registers the repo under its local name and downloads its index,
// which is what makes "<chart-repo>/<chart-name>" resolvable by the SDK.
func AddRepo(settings *cli.EnvSettings, name, url string) (*repo.IndexFile, error) {
	for _, dir := range []string{filepath.Dir(settings.RepositoryConfig), settings.RepositoryCache} {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return nil, err
		}
	}

	entry := &repo.Entry{Name: name, URL: url}
	chartRepo, err := repo.NewChartRepository(entry, getter.All(settings))
	if err != nil {
		return nil, fmt.Errorf("chart repository %s (%s): %w", name, url, err)
	}
	chartRepo.CachePath = settings.RepositoryCache

	indexPath, err := chartRepo.DownloadIndexFile()
	if err != nil {
		return nil, fmt.Errorf("download index from %s: %w", url, err)
	}
	index, err := repo.LoadIndexFile(indexPath)
	if err != nil {
		return nil, fmt.Errorf("load index %s: %w", indexPath, err)
	}

	repoFile := repo.NewFile()
	if existing, err := repo.LoadFile(settings.RepositoryConfig); err == nil {
		repoFile = existing
	}
	repoFile.Update(entry)
	if err := repoFile.WriteFile(settings.RepositoryConfig, 0o644); err != nil {
		return nil, fmt.Errorf("write %s: %w", settings.RepositoryConfig, err)
	}
	return index, nil
}

// Upgrade resolves the chart from the registered repo and upgrades the release.
func Upgrade(cfg *action.Configuration, settings *cli.EnvSettings, o Options) (*release.Release, error) {
	if _, err := AddRepo(settings, o.ChartRepo, o.ChartRepoURL); err != nil {
		return nil, err
	}

	up := action.NewUpgrade(cfg)
	up.Namespace = o.Namespace
	up.Version = o.Version
	up.Timeout = o.Timeout
	// An unattended upgrade must keep the user's prior values AND pick up any
	// new keys the target chart's defaults introduce (e.g. a values tree that
	// didn't exist in the installed release's chart version). ReuseValues alone
	// would silently drop new chart defaults; ResetThenReuseValues loads the
	// new chart's defaults first, then reapplies the user's previous values on
	// top of them.
	up.ResetThenReuseValues = true

	ref := o.ChartRepo + "/" + o.ChartName
	chartPath, err := up.ChartPathOptions.LocateChart(ref, settings)
	if err != nil {
		return nil, fmt.Errorf("locate chart %s: %w", ref, err)
	}
	ch, err := loader.Load(chartPath)
	if err != nil {
		return nil, fmt.Errorf("load chart %s: %w", chartPath, err)
	}

	slog.Info("upgrading release",
		"release", o.Release, "namespace", o.Namespace,
		"chart", ref, "version", ch.Metadata.Version)

	rel, err := up.Run(o.Release, ch, map[string]any{})
	if err != nil {
		return nil, fmt.Errorf("upgrade release %s: %w", o.Release, err)
	}
	slog.Info("upgraded release", "release", rel.Name, "revision", rel.Version, "status", rel.Info.Status.String())
	return rel, nil
}
