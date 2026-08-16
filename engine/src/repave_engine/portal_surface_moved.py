"""Pointer pages for HTML surfaces that now live in Backstage."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MovedSurface:
    surface_id: str
    title: str
    lead: str
    backstage_label: str
    backstage_path: str
    api_hint: str
    cli_hint: str
    nav_active: str


def moved_page_context(surface: MovedSurface) -> dict[str, object]:
    return {
        "nav_active": surface.nav_active,
        "moved_surface_id": surface.surface_id,
        "moved_title": surface.title,
        "moved_lead": surface.lead,
        "moved_backstage_label": surface.backstage_label,
        "moved_backstage_path": surface.backstage_path,
        "moved_api_hint": surface.api_hint,
        "moved_cli_hint": surface.cli_hint,
    }


def _surface(
    surface_id: str,
    *,
    title: str,
    lead: str,
    backstage_label: str,
    backstage_path: str,
    api_hint: str,
    cli_hint: str,
    nav_active: str,
) -> MovedSurface:
    return MovedSurface(
        surface_id=surface_id,
        title=title,
        lead=lead,
        backstage_label=backstage_label,
        backstage_path=backstage_path,
        api_hint=api_hint,
        cli_hint=cli_hint,
        nav_active=nav_active,
    )


CATALOG_MOVED = _surface(
    "catalog",
    title="Catalog moved",
    lead="Golden-path browse now lives in Backstage. This HTML catalog is gone.",
    backstage_label="Generate",
    backstage_path="/generate",
    api_hint="GET /api/v2/catalog/blueprints",
    cli_hint="repave generate <blueprint>",
    nav_active="catalog",
)

LIBRARY_MOVED = _surface(
    "library",
    title="Library moved",
    lead="Created repos now live in the Backstage library.",
    backstage_label="Library",
    backstage_path="/library",
    api_hint="GET /api/v2/library",
    cli_hint="GET /api/v2/library",
    nav_active="library",
)

HOME_MOVED = _surface(
    "home",
    title="My services moved",
    lead="Your services now live under Backstage My services.",
    backstage_label="My services",
    backstage_path="/my-services",
    api_hint="GET /api/v2/catalog/entities",
    cli_hint="GET /api/v2/catalog/entities",
    nav_active="home",
)

SERVICES_MOVED = _surface(
    "services",
    title="Service page moved",
    lead="Service detail now lives in Backstage.",
    backstage_label="Services",
    backstage_path="/services",
    api_hint="GET /api/v2/catalog/entities/{id}",
    cli_hint="GET /api/v2/catalog/entities/{id}",
    nav_active="library",
)

TEAMS_MOVED = _surface(
    "teams",
    title="Team page moved",
    lead="Team views now live in Backstage.",
    backstage_label="Teams",
    backstage_path="/teams",
    api_hint="GET /api/v2/catalog/entities?team=",
    cli_hint="GET /api/v2/catalog/entities?team=",
    nav_active="home",
)

ACTIVITY_MOVED = _surface(
    "activity",
    title="Activity moved",
    lead="Run history now lives in Backstage Activity.",
    backstage_label="Activity",
    backstage_path="/activity",
    api_hint="GET /api/v2/runs",
    cli_hint="GET /api/v2/runs",
    nav_active="activity",
)

ESTATE_MOVED = _surface(
    "estate",
    title="Estate moved",
    lead="Estate map now lives in Backstage.",
    backstage_label="Estate",
    backstage_path="/estate",
    api_hint="GET /api/v2/fleet",
    cli_hint="GET /api/v2/fleet",
    nav_active="estate",
)

IMPORT_MOVED = _surface(
    "import",
    title="Import moved",
    lead="Brownfield import now lives in Backstage.",
    backstage_label="Import",
    backstage_path="/import",
    api_hint="POST /api/v2/imports/plan",
    cli_hint="repave import",
    nav_active="import",
)

IMPORT_BATCH_MOVED = _surface(
    "import-batch",
    title="Batch import moved",
    lead="Org scan and batch import now live in Backstage.",
    backstage_label="Batch import",
    backstage_path="/import/batch",
    api_hint="POST /api/v2/github/org-scan",
    cli_hint="repave import --batch",
    nav_active="import",
)

VERIFY_MOVED = _surface(
    "verify",
    title="Verify moved",
    lead="Estate verify now lives in Backstage.",
    backstage_label="Verify",
    backstage_path="/verify",
    api_hint="POST /api/v2/verify",
    cli_hint="repave verify",
    nav_active="verify",
)

RESULT_MOVED = _surface(
    "result",
    title="Results moved",
    lead="Generate results now live in Backstage Generate.",
    backstage_label="Generate",
    backstage_path="/generate",
    api_hint="POST /api/v2/generate",
    cli_hint="repave generate <blueprint>",
    nav_active="catalog",
)

BUNDLE_MOVED = _surface(
    "bundle",
    title="Bundle form moved",
    lead="Bundle generate now lives in Backstage Bundles. This HTML form is gone.",
    backstage_label="Bundles",
    backstage_path="/bundles",
    api_hint="GET /api/v2/bundles/{name}",
    cli_hint="repave generate --bundle <name>",
    nav_active="catalog",
)

BUNDLE_RESULT_MOVED = _surface(
    "bundle-result",
    title="Bundle results moved",
    lead="Bundle generate results now live in Backstage Bundles.",
    backstage_label="Bundles",
    backstage_path="/bundles",
    api_hint="POST /api/v2/generate",
    cli_hint="repave generate --bundle <name>",
    nav_active="catalog",
)

UPGRADE_MOVED = _surface(
    "upgrade",
    title="Upgrade moved",
    lead="Upgrade preview now lives in Backstage. This HTML form is gone.",
    backstage_label="Upgrade",
    backstage_path="/upgrade",
    api_hint="POST /api/v2/upgrades/plan",
    cli_hint="repave plan-upgrade --target-repo <path>",
    nav_active="update",
)

_PLATFORM_PAGES: dict[str, tuple[str, str, str, str]] = {
    "fleet": ("Fleet", "/fleet", "GET /api/v2/fleet", "GET /api/v2/fleet"),
    "ops": ("Ops", "/ops", "GET /api/v2/platform/ops", "GET /api/v2/platform/ops"),
    "standards": (
        "Standards",
        "/standards",
        "GET /api/v2/platform/standards",
        "GET /api/v2/platform/standards",
    ),
    "campaigns": (
        "Campaigns",
        "/campaigns",
        "GET /api/v2/platform/campaigns",
        "GET /api/v2/platform/campaigns",
    ),
    "finops": ("FinOps", "/finops", "GET /api/v2/platform/finops", "GET /api/v2/platform/finops"),
    "adoption": (
        "Adoption",
        "/adoption",
        "GET /api/v2/platform/adoption",
        "GET /api/v2/platform/adoption",
    ),
    "compliance": (
        "Compliance",
        "/compliance",
        "GET /api/v2/platform/compliance",
        "GET /api/v2/platform/compliance",
    ),
    "value-stream": (
        "Value stream",
        "/value-stream",
        "GET /api/v2/platform/value-stream",
        "GET /api/v2/platform/value-stream",
    ),
    "roadmap": (
        "Roadmap",
        "/roadmap",
        "GET /api/v2/platform/roadmap-evidence",
        "GET /api/v2/platform/roadmap-evidence",
    ),
    "feedback": (
        "Feedback",
        "/feedback",
        "GET /api/v2/platform/feedback",
        "POST /api/v2/platform/feedback",
    ),
    "maturity": (
        "Maturity",
        "/maturity",
        "GET /api/v2/catalog/entities",
        "GET /api/v2/catalog/entities",
    ),
    "initiatives": (
        "Initiatives",
        "/maturity",
        "GET /api/v2/catalog/initiatives",
        "GET /api/v2/catalog/initiatives",
    ),
}


def platform_moved(page: str) -> MovedSurface:
    label, path, api_hint, cli_hint = _PLATFORM_PAGES[page]
    return _surface(
        f"platform-{page}",
        title=f"{label} moved",
        lead=f"{label} now lives in Backstage.",
        backstage_label=label,
        backstage_path=path,
        api_hint=api_hint,
        cli_hint=cli_hint,
        nav_active="platform",
    )
