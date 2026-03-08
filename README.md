# Makestack Addons

Official addon registry and first-party packages for [Makestack](https://github.com/makestack/makestack-shell).

This repository serves a dual purpose: it is both the **registry index** (read by the Shell's package installer) and the **host** for all first-party addon packages. Each package lives in its own subdirectory and can be installed directly from a local path or via the registry.

---

## Packages

| Name | Type | Description |
|------|------|-------------|
| `inventory-stock` | module | Track material and tool stock quantities, units, and reorder thresholds |
| `costing` | module | Record purchase prices and calculate project material costs |
| `suppliers` | module | Manage supplier and vendor contacts linked to catalogue entries |
| `extended-widgets` | widget-pack | Keyword renderers for stock levels, costs, and supplier references |
| `leatherworking-starter` | catalogue | Starter catalogue: essential leatherworking tools, materials, techniques, and workflows |
| `forge-theme` | data | Forge theme — dark industrial palette with steel and amber accents |

---

## Using as a Registry

Add this repository as a registry source so the Shell can discover packages from it:

```bash
makestack registry add https://raw.githubusercontent.com/makestack/makestack-addons/main/index.json
```

Once added, packages appear in `makestack registry list` and can be installed by name:

```bash
makestack install inventory-stock
makestack install costing
makestack install suppliers
makestack install extended-widgets
makestack install leatherworking-starter
makestack install forge-theme
```

---

## Local Install

When working with this repository directly (development or self-hosted), install packages by path:

```bash
# Modules
makestack install ./modules/inventory-stock
makestack install ./modules/costing
makestack install ./modules/suppliers

# Widget pack
makestack install ./widget-packs/extended-widgets

# Catalogue
makestack install ./catalogues/leatherworking-starter

# Theme
makestack install ./themes/forge
```

---

## Structure

```
makestack-addons/
├── index.json                          # Registry index — package discovery manifest
├── modules/
│   ├── inventory-stock/                # Module: stock quantity tracking
│   │   ├── makestack-package.json
│   │   ├── manifest.json
│   │   ├── backend/
│   │   │   ├── __init__.py
│   │   │   ├── routes.py
│   │   │   └── migrations/
│   │   │       └── 001_create_stock_tables.py
│   │   └── frontend/
│   │       ├── index.ts
│   │       └── keywords.ts
│   ├── costing/                        # Module: purchase price recording
│   │   └── ...
│   └── suppliers/                      # Module: vendor and sourcing contacts
│       └── ...
├── widget-packs/
│   └── extended-widgets/               # Widget pack: standalone keyword renderers
│       ├── makestack-package.json
│       ├── index.ts
│       └── components/
│           ├── StockLevel.tsx
│           ├── CostBadge.tsx
│           └── SupplierRef.tsx
├── catalogues/
│   └── leatherworking-starter/         # Catalogue: leatherworking primitives
│       ├── makestack-package.json
│       ├── tools/
│       ├── materials/
│       ├── techniques/
│       └── workflows/
└── themes/
    └── forge/                          # Data package: Forge dark theme
        ├── makestack-package.json
        └── forge.json
```

### Package types

- **module** — Backend (FastAPI routes + SQLite migrations) and frontend (keyword renderers). Mounted into the Shell at `/api/modules/<name>/`.
- **widget-pack** — Frontend-only keyword renderers. No backend. Useful when you want display components without a database.
- **catalogue** — A collection of primitive manifests (tools, materials, techniques, workflows, projects, events) to be imported into Core's Git-backed catalogue.
- **data** — Arbitrary files copied to target paths (e.g. theme JSON files placed under `.makestack/themes/`).

---

## Monorepo vs Individual Repos

All first-party packages live here in a single monorepo for ease of development and versioning. When this project is published to GitHub, the registry `index.json` at the repo root points to `https://github.com/makestack/makestack-addons` for all packages — the Shell's registry client resolves the correct subdirectory by package name and type.

Third-party packages live in their own separate repositories and register themselves by submitting a PR to add an entry to `index.json`.
