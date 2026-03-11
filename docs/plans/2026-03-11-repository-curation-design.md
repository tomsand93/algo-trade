# Repository Curation Design

Date: 2026-03-11
Scope: `C:\Users\Tom1\Desktop\TRADING\algo-trade`

## Goal

Turn `algo-trade` into a clean, professional, Git-ready repository without deleting local project content from disk.

## Repository Policy

- Keep the Git-visible repo focused on active, meaningful code.
- Do not delete local content during cleanup.
- Preserve non-core or noisy content locally by excluding it from Git with `.gitignore`.
- Prefer a simple top-level structure over a storage-oriented workspace layout.

## Active Repository Surface

The curated repository should center on:

- `strategies/`
- `resources/`
- `docs/`
- Root project files such as `README.md` and `.gitignore`

Recommended Git-visible structure:

```text
algo-trade/
├── README.md
├── .gitignore
├── docs/
├── resources/
│   ├── multi-account-manager/
│   └── shared/
└── strategies/
    ├── candlestick-pro/
    ├── fvg-breakout/
    ├── insider/
    ├── orderbook/
    └── stock-screener/
```

## Classification Rules

### Keep tracked

- Strategy modules with coherent code, documentation, and tests
- Shared operational tooling in `resources/`
- Documentation that describes the current repository accurately
- Lightweight reference material only if it is intentional and useful

### Keep locally but exclude from Git

- Legacy snapshots
- Old experiments
- Scratch areas
- Local logs
- Downloaded datasets
- Generated plots, reports, and result files
- Virtual environments and caches
- Local machine or scheduler artifacts

### Rename or rewrite

- Misleading root onboarding files
- Inconsistent docs that still describe the parent `TRADING` workspace instead of `algo-trade`
- Weakly named utility or support files that are worth keeping

## Folder Decisions

### `strategies/`

Primary active code surface. Review each strategy for completeness, duplicate scripts, generated artifacts, and documentation quality.

### `resources/`

Keep as the shared infrastructure surface. Add missing top-level documentation if needed.

### `docs/`

Keep only repo-accurate documentation. Add a plan record for the cleanup and reduce stale summary noise where appropriate.

### `reference/`

Keep only if it is intentionally part of the repo and lightweight enough to justify its presence.

### `archive/`, `research/`, `trading/`, `tradingView/`

Treat as non-core by default. Preserve them locally but exclude them from Git unless specific code is later promoted into the curated repository.

## Cleanup Work

1. Audit top-level folders and identify what belongs to the curated repo surface.
2. Scan for secrets, hardcoded local paths, and machine-specific configuration.
3. Create a professional `.gitignore` that excludes generated and local-only material.
4. Replace the root onboarding story with a root `README.md` that matches `algo-trade`.
5. Improve entry points and module descriptions for the tracked repo.
6. Show the final Git-visible tree before push.

## Risks

- Some non-core folders may contain useful code that is not yet obvious from filenames alone.
- Existing docs may conflict with the new curated story and need rewriting, not just minor edits.
- Git operations may be blocked until the repository is marked as a safe directory for the current user context.

## Validation

- Root README explains the repo in one screen.
- `.gitignore` excludes local-only and generated material.
- Active top-level folders are limited to curated code and documentation.
- Sensitive information is not left in tracked config files.
- Final tree is easy to scan and suitable for GitHub presentation.
