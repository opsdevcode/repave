from __future__ import annotations

# Galaxy Name:version pairs allowed in advanced platform picker (ansible-role-generic).
GALAXY_PLATFORM_ENUM: tuple[str, ...] = (
    "EL:9",
    "EL:8",
    "Ubuntu:noble",
    "Ubuntu:jammy",
    "Ubuntu:focal",
    "Debian:bookworm",
    "Debian:bullseye",
    "Windows:2022",
    "Windows:2019",
    "Windows:2016",
)

# Estate defaults when support_linux is enabled (standards/ansible/role-standard.md).
LINUX_DEFAULT_PLATFORMS: tuple[str, ...] = ("EL:9", "Ubuntu:jammy", "Debian:bookworm")

WINDOWS_GENERATION_TO_GALAXY: dict[str, str] = {
    "2022": "Windows:2022",
    "2019": "Windows:2019",
}


def parse_support_flag(raw: object, *, default: bool) -> bool:
    if raw in (None, ""):
        return default
    text = str(raw).strip().lower()
    if text in ("true", "1", "yes", "on"):
        return True
    if text in ("false", "0", "no", "off"):
        return False
    raise ValueError(f"invalid boolean flag: {raw!r}")


def _parse_advanced_platforms(raw: object) -> list[str]:
    if raw in (None, "", "[]"):
        return []
    if isinstance(raw, list):
        items = [str(item).strip() for item in raw if str(item).strip()]
    else:
        items = [part.strip() for part in str(raw).split(",") if part.strip()]
    invalid = [item for item in items if item not in GALAXY_PLATFORM_ENUM]
    if invalid:
        allowed = ", ".join(GALAXY_PLATFORM_ENUM)
        bad = ", ".join(invalid)
        raise ValueError(f"Invalid target_platforms_advanced: {bad!r}. Allowed: {allowed}")
    return sorted(set(items))


def resolve_target_platforms(
    *,
    support_linux: bool,
    support_windows: bool,
    windows_server_generation: str,
    target_platforms_advanced: object,
) -> str:
    advanced = _parse_advanced_platforms(target_platforms_advanced)
    if advanced:
        return ",".join(advanced)

    platforms: list[str] = []
    if support_linux:
        platforms.extend(LINUX_DEFAULT_PLATFORMS)
    if support_windows:
        generation = str(windows_server_generation or "2022").strip()
        galaxy = WINDOWS_GENERATION_TO_GALAXY.get(generation)
        if galaxy is None:
            allowed = ", ".join(sorted(WINDOWS_GENERATION_TO_GALAXY))
            raise ValueError(
                f"Invalid windows_server_generation: {generation!r}. Allowed: {allowed}"
            )
        platforms.append(galaxy)

    if not platforms:
        raise ValueError("Enable Linux and/or Windows support, or use advanced platform list")

    return ",".join(sorted(set(platforms)))


def target_platforms_list(resolved_csv: str) -> list[str]:
    return [part.strip() for part in resolved_csv.split(",") if part.strip()]


def infer_platform_form_values(resolved: list[str]) -> dict[str, str]:
    """Map stored Galaxy platforms back to portal form fields when possible."""
    platform_set = set(resolved)
    linux_defaults = set(LINUX_DEFAULT_PLATFORMS)

    for generation, galaxy in WINDOWS_GENERATION_TO_GALAXY.items():
        if platform_set == linux_defaults | {galaxy}:
            return {
                "support_linux": "true",
                "support_windows": "true",
                "windows_server_generation": generation,
                "target_platforms_advanced": "",
            }

    if platform_set == linux_defaults:
        return {
            "support_linux": "true",
            "support_windows": "false",
            "windows_server_generation": "2022",
            "target_platforms_advanced": "",
        }

    if platform_set == {WINDOWS_GENERATION_TO_GALAXY["2022"]}:
        return {
            "support_linux": "false",
            "support_windows": "true",
            "windows_server_generation": "2022",
            "target_platforms_advanced": "",
        }

    if platform_set == {WINDOWS_GENERATION_TO_GALAXY["2019"]}:
        return {
            "support_linux": "false",
            "support_windows": "true",
            "windows_server_generation": "2019",
            "target_platforms_advanced": "",
        }

    return {
        "support_linux": "true",
        "support_windows": "false",
        "windows_server_generation": "2022",
        "target_platforms_advanced": ",".join(sorted(platform_set)),
    }
