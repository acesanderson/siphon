"""
Siphon sync command - bulk ingest an Obsidian vault into Siphon.

Vault walking and change detection happen client-side. Processing
(extract → enrich → store) goes through HeadwaterAsyncClient so the full
server-side pipeline runs. After all notes are processed, a single embed-batch
call generates vectors for every changed note, rather than one call per note.

Reads vault path from --vault flag or ~/.config/siphon/config.toml (key: vault).
"""
from __future__ import annotations

import asyncio
import tomllib
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import TYPE_CHECKING

import click

from siphon_client.cli.printer import Printer

if TYPE_CHECKING:
    pass

DEFAULT_BLOCKLIST: set[str] = {".obsidian", "templates", "_attachments"}
_BLOCKLIST_PATH = Path.home() / ".config" / "siphon" / "obsidian_blocklist.txt"

_HOOK_SCRIPT = """\
#!/bin/bash
# Installed by: siphon sync --install-hook
# Runs after every git pull/merge; only syncs if .md files changed.
changed=$(git diff-tree -r --name-only --no-commit-id ORIG_HEAD HEAD 2>/dev/null | grep '\\.md$')
if [ -n "$changed" ]; then
    siphon sync
fi
"""


@dataclass
class SyncStats:
    new: int = 0
    updated: int = 0
    pruned: int = 0
    skipped: int = 0
    empty_skipped: int = 0
    embed_ok: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = []
        if self.new:
            parts.append(f"{self.new} new")
        if self.updated:
            parts.append(f"{self.updated} updated")
        if self.pruned:
            parts.append(f"{self.pruned} pruned")
        if self.skipped:
            parts.append(f"{self.skipped} skipped")
        if self.empty_skipped:
            parts.append(f"{self.empty_skipped} empty")
        if self.embed_ok:
            parts.append(f"{self.embed_ok} embedded")
        if self.errors:
            parts.append(f"{len(self.errors)} errors")
        return ", ".join(parts) if parts else "nothing to do"


def _default_vault() -> Path | None:
    config_path = Path.home() / ".config" / "siphon" / "config.toml"
    if config_path.exists():
        with open(config_path, "rb") as f:
            cfg = tomllib.load(f)
        vault = cfg.get("vault")
        if vault:
            return Path(vault).expanduser()
    return None


def _load_blocklist() -> set[str]:
    if _BLOCKLIST_PATH.exists():
        entries = {
            line.strip()
            for line in _BLOCKLIST_PATH.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        }
        return entries or DEFAULT_BLOCKLIST
    return DEFAULT_BLOCKLIST


def _is_blocked(path: Path, vault_root: Path, blocklist: set[str]) -> bool:
    try:
        rel = path.relative_to(vault_root)
    except ValueError:
        return False
    return any(part in blocklist for part in rel.parts)


def _collect_notes(vault_root: Path, blocklist: set[str]) -> list[Path]:
    return [
        p for p in vault_root.rglob("*.md")
        if not _is_blocked(p, vault_root, blocklist)
    ]


def _is_empty(path: Path) -> bool:
    """Return True if the file has no meaningful content."""
    if path.stat().st_size == 0:
        return True
    return not path.read_text(encoding="utf-8", errors="replace").strip()


def _install_hook(vault_path: Path, printer: Printer) -> None:
    git_dir = vault_path / ".git"
    if not git_dir.is_dir():
        printer.print_pretty(
            f"[red]Error:[/red] {vault_path} is not a git repository."
        )
        raise click.Abort()

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    hook_path = hooks_dir / "post-merge"

    if hook_path.exists():
        printer.print_pretty(
            f"[yellow]Warning:[/yellow] {hook_path} already exists — overwriting."
        )

    hook_path.write_text(_HOOK_SCRIPT)
    hook_path.chmod(0o755)
    printer.print_pretty(f"[green]Installed:[/green] {hook_path}")


async def _process_note(
    uri: str,
    note_path: Path,
    is_new: bool,
    semaphore: asyncio.Semaphore,
    client,
    stats: SyncStats,
    printer: Printer,
) -> str | None:
    """Process one note through the pipeline. Returns the URI on success, None on error."""
    from siphon_api.api.siphon_request import SiphonRequestParams
    from siphon_api.api.to_siphon_request import create_siphon_request
    from siphon_api.enums import ActionType

    async with semaphore:
        try:
            params = SiphonRequestParams(action=ActionType.GULP, use_cache=False)
            request = create_siphon_request(
                source=str(note_path.resolve()),
                request_params=params,
            )
            await client.siphon.process(request)
            if is_new:
                stats.new += 1
            else:
                stats.updated += 1
            return uri
        except Exception as e:
            printer.print_pretty(f"  [red]error:[/red] {note_path.name}: {e}")
            stats.errors.append(str(note_path))
            return None


async def _run_sync_async(
    vault_path: Path,
    dry_run: bool,
    concurrency: int,
    printer: Printer,
) -> SyncStats:
    from siphon_api.enums import SourceType
    from siphon_server.database.postgres.repository import ContentRepository

    stats = SyncStats()
    repository = ContentRepository()
    blocklist = _load_blocklist()
    vault_root = vault_path.resolve()

    note_paths = _collect_notes(vault_root, blocklist)
    printer.print_pretty(f"Found {len(note_paths)} notes in {vault_root}")

    current_uris: dict[str, Path] = {
        f"obsidian:///{p.stem}": p for p in note_paths
    }

    existing_uris: set[str] = set(
        repository.get_all_uris_by_source_type(SourceType.OBSIDIAN)
    )

    to_process: list[tuple[str, Path, bool]] = []

    for uri, note_path in current_uris.items():
        if uri not in existing_uris:
            to_process.append((uri, note_path, True))
            continue
        existing = repository.get(uri)
        file_mtime = int(note_path.stat().st_mtime)
        if existing and file_mtime <= existing.updated_at:
            stats.skipped += 1
        else:
            to_process.append((uri, note_path, False))

    # Pre-filter: skip empty files before sending through the pipeline.
    # Empty notes waste an LLM enrichment call and produce nothing worth embedding.
    filtered_to_process: list[tuple[str, Path, bool]] = []
    for uri, note_path, is_new in to_process:
        if _is_empty(note_path):
            stats.empty_skipped += 1
        else:
            filtered_to_process.append((uri, note_path, is_new))

    if dry_run:
        for _, _, is_new in filtered_to_process:
            if is_new:
                stats.new += 1
            else:
                stats.updated += 1
        stats.embed_ok = len(filtered_to_process)  # would-be embed count
    elif filtered_to_process:
        from headwater_client.client.headwater_client_async import HeadwaterAsyncClient

        semaphore = asyncio.Semaphore(concurrency)
        async with HeadwaterAsyncClient() as client:
            results = await asyncio.gather(*[
                _process_note(uri, note_path, is_new, semaphore, client, stats, printer)
                for uri, note_path, is_new in filtered_to_process
            ])

            processed_uris = [r for r in results if r is not None]

            if processed_uris:
                try:
                    embed_result = await client.siphon.embed_batch(processed_uris)
                    stats.embed_ok = embed_result.embedded
                except Exception as e:
                    printer.print_pretty(
                        f"  [yellow]warning:[/yellow] embed-batch failed: {e}"
                    )

    stale_uris = existing_uris - set(current_uris.keys())
    if not dry_run:
        for uri in stale_uris:
            repository.delete(uri)
            stats.pruned += 1
    else:
        stats.pruned = len(stale_uris)

    return stats


def _run_sync(vault_path: Path, dry_run: bool, concurrency: int, printer: Printer) -> SyncStats:
    return asyncio.run(_run_sync_async(vault_path, dry_run, concurrency, printer))


@click.command()
@click.option(
    "--vault",
    "-v",
    default=None,
    help="Path to Obsidian vault (defaults to 'vault' key in ~/.config/siphon/config.toml)",
)
@click.option(
    "--install-hook",
    is_flag=True,
    help="Install a git post-merge hook in the vault repo that auto-syncs on pull",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview what would change without writing to the database",
)
@click.option(
    "--concurrency",
    "-c",
    default=10,
    type=int,
    show_default=True,
    help="Max simultaneous requests to headwater",
)
@click.option(
    "--raw",
    is_flag=True,
    help="Force raw output mode",
)
def sync(
    vault: str | None,
    install_hook: bool,
    dry_run: bool,
    concurrency: int,
    raw: bool,
) -> None:
    """
    Sync an Obsidian vault into Siphon.

    New and changed notes are processed through the full headwater pipeline
    (extract → enrich → store) with up to CONCURRENCY requests in flight
    simultaneously. Unchanged notes are skipped. Empty notes are skipped
    entirely. After all notes are processed, a single embed-batch call
    generates vectors for every successfully processed note. Notes removed
    from disk are pruned from the database.

    Examples:
        siphon sync --vault ~/morphy
        siphon sync                    # uses vault from config.toml
        siphon sync --install-hook     # write git post-merge hook
        siphon sync --dry-run
        siphon sync --concurrency 20   # push harder on first sync
    """
    printer = Printer(raw=raw)

    vault_path: Path | None = Path(vault).expanduser() if vault else _default_vault()
    if vault_path is None:
        printer.print_pretty(
            "[red]Error:[/red] No vault path provided. "
            "Use --vault or set 'vault' in ~/.config/siphon/config.toml"
        )
        raise click.Abort()

    if not vault_path.is_dir():
        printer.print_pretty(f"[red]Error:[/red] Vault not found: {vault_path}")
        raise click.Abort()

    if install_hook:
        _install_hook(vault_path, printer)
        return

    dry_label = " [dim](dry run)[/dim]" if dry_run else ""
    with printer.status(f"Syncing vault {vault_path}{dry_label}..."):
        stats = _run_sync(vault_path, dry_run, concurrency, printer)

    prefix = "[dim]dry run:[/dim] " if dry_run else ""
    printer.print_pretty(f"{prefix}Sync complete — {stats.summary()}")
