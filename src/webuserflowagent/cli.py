from __future__ import annotations

import argparse
from pathlib import Path

from .manifest import load, save
from .models import ApplicationManifest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="webuserflow", description="WebUserFlowAgent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create an application manifest")
    init_parser.add_argument("--name", required=True, help="Application name")
    init_parser.add_argument("--base-url", required=True, help="Application base URL")
    init_parser.add_argument("--output", type=Path, help="Output JSON path")

    validate_parser = subparsers.add_parser("validate", help="Validate a manifest")
    validate_parser.add_argument("path", type=Path)

    explore_parser = subparsers.add_parser("explore", help="Discover interactive elements on a page")
    explore_parser.add_argument("url", help="Page URL to explore")
    explore_parser.add_argument("--name", required=True, help="Application name")
    explore_parser.add_argument("--output", type=Path, help="Output JSON path")
    explore_parser.add_argument("--headed", action="store_true", help="Show the browser window")
    explore_parser.add_argument("--timeout", type=int, default=30_000, help="Navigation timeout in milliseconds")
    explore_parser.add_argument("--screenshot", type=Path, help="Optional full-page screenshot path")
    explore_parser.add_argument(
        "--keep-cookies",
        action="store_true",
        help="Do not dismiss a recognized cookie consent dialog",
    )
    explore_parser.add_argument(
        "--search",
        metavar="QUERY",
        help="Run a search after the page is ready and capture the results state",
    )

    flow_parser = subparsers.add_parser(
        "flow", help="Discover multi-step flows by clicking through the site (Flow Agent)"
    )
    flow_parser.add_argument("url", help="Starting page URL")
    flow_parser.add_argument("--name", required=True, help="Application name")
    flow_parser.add_argument("--output", type=Path, help="Output JSON path")
    flow_parser.add_argument("--headed", action="store_true", help="Show the browser window")
    flow_parser.add_argument("--timeout", type=int, default=30_000, help="Navigation timeout in milliseconds")
    flow_parser.add_argument("--max-pages", type=int, default=8, help="Max distinct states to discover")
    flow_parser.add_argument("--max-actions-per-page", type=int, default=6, help="Max candidate clicks tried per state")
    flow_parser.add_argument("--max-depth", type=int, default=3, help="Max clicks from the starting page")
    flow_parser.add_argument(
        "--keep-cookies",
        action="store_true",
        help="Do not dismiss a recognized cookie consent dialog",
    )
    flow_parser.add_argument(
        "--browser", choices=["chromium", "firefox", "webkit", "edge"], default="chromium",
        help="Browser engine to use (default: chromium). 'edge' launches the "
             "installed Microsoft Edge via Playwright's chromium driver.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "init":
        output = args.output or Path("data/manifests") / f"{args.name}.json"
        save(ApplicationManifest(name=args.name, base_url=args.base_url), output)
        print(f"Manifest created: {output}")
        return 0

    if args.command == "validate":
        manifest = load(args.path)
        print(f"Valid manifest: {manifest.name} ({len(manifest.pages)} pages, {len(manifest.flows)} flows)")
        return 0

    if args.command == "flow":
        from .flow import explore_flows

        output = args.output or Path("data/manifests") / f"{args.name}.json"
        manifest = explore_flows(
            args.url,
            args.name,
            headless=not args.headed,
            timeout_ms=args.timeout,
            max_pages=args.max_pages,
            max_actions_per_page=args.max_actions_per_page,
            max_depth=args.max_depth,
            dismiss_cookies=not args.keep_cookies,
            browser_name=args.browser,
        )
        save(manifest, output)
        element_count = sum(len(page.elements) for page in manifest.pages)
        print(
            f"Flow exploration complete: {len(manifest.pages)} states, "
            f"{len(manifest.transitions)} transitions, {len(manifest.flows)} flows, "
            f"{element_count} elements"
        )
        print(f"Manifest created: {output}")
        return 0

    from .explorer import explore_page

    output = args.output or Path("data/manifests") / f"{args.name}.json"
    screenshot = str(args.screenshot) if args.screenshot else None
    manifest = explore_page(
        args.url,
        args.name,
        headless=not args.headed,
        timeout_ms=args.timeout,
        screenshot_path=screenshot,
        dismiss_cookies=not args.keep_cookies,
        search_query=args.search,
    )
    save(manifest, output)
    element_count = sum(len(page.elements) for page in manifest.pages)
    print(
        f"Exploration complete: {len(manifest.pages)} states, "
        f"{len(manifest.transitions)} transitions, {element_count} elements"
    )
    print(f"Manifest created: {output}")
    challenges = [page for page in manifest.pages if page.state_type == "challenge"]
    if challenges:
        print(
            "Warning: navigation reached a security challenge; "
            "it was recorded but not bypassed."
        )
    return 0
