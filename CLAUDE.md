# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

This is the **source-of-truth asset + catalog-generation repo** for "Sugoi Posters", an otaku/anime
merchandise store (`https://sugoipostershn.com`). It holds the product images (`.webp`) organized
into a strict folder tree, plus Python/PowerShell scripts and a GitHub Actions workflow that:

1. Normalizes image filenames to clean ASCII (`Quitar_espacios.py`).
2. Generates `products.dart` pointing to the store's own Cloudflare R2 CDN
   (`https://img.sugoipostershn.com/`) and auto-copies it to `../SugoiPosters-Web-App/lib/data/products.dart`.
3. Automatically syncs originals + generated WebP thumbnails (`_thumbs/360/` and `_thumbs/640/`)
   to the **Cloudflare R2** bucket `sugoi-posters-assets` on every `git push` to `main`.

There is no application here, no test suite, and no package manifest. Everything is in Spanish
(folder names, product fields, script output).

## Core workflow (Cloudflare R2 bucket pipeline)

The whole pipeline is driven by file/folder *layout*, not by data files.

### Adding or editing products
1. Drop new images into `C-a/`, `S-u/`, `P-o/`, `S-e/`, or `Pol/`.
2. Convert & organize locally:
   ```bash
   python convertir.py            # 1. PNG/JPG/JPEG → WebP (q85); deletes originals
   python organizar_carpetas.py   # 2. (interactive) wrap loose images into Foo/Foo.webp folders
   python Renombrar.py            # 3. (interactive) normalize __/##, renumber siblings _1.._n
   ```
3. Normalize ASCII, regenerate `products.dart`, sync Cloudflare R2, and deploy the web app:
   ```powershell
   # Recommended all-in-one flow (normalizes -> products.dart -> git push -> waits R2 green -> Firebase deploy):
   .\publicar_catalogo.ps1 -Deploy -Message "feat(catalogo): descripcion"

   # Or step-by-step:
   python Quitar_espacios.py      # 4. spaces, '#' and non-ASCII (N°8 -> No_8, ō -> o, etc.) → ASCII
   python productos.py            # 5. regenerate products.dart + auto-copy to SugoiPosters-Web-App
   git add -A && git commit -m "..." && git push origin main
   # 6. Wait for GitHub Actions "Sync Assets to Cloudflare R2" to succeed before deploying Web App
   ```

Only `convertir.py` (argparse), `Quitar_espacios.py` (`--dry-run`), `productos.py`, and `sync_r2.py`
are non-interactive. `organizar_carpetas.py` and `Renombrar.py` prompt via `input()` (and
`buscar_carpetas_una_imagen.py` opens a Tk dialog), so do not run them unattended.

## Cloudflare R2 CDN & GitHub Actions sync

- **Bucket:** `sugoi-posters-assets` (Cloudflare R2, ENAM, CORS `AllowedOrigins: ["*"]` for Skwasm/COEP).
- **Public Custom Domain:** `https://img.sugoipostershn.com/` (TLS 1.2+, Cloudflare Edge caching).
- **Sync script:** `sync_r2.py`
  - Uploads originals from `C-a`, `S-u`, `P-o`, `S-e`, `Pol` with
    `Cache-Control: public, max-age=31536000, immutable` and `Content-Type: image/webp`.
  - Generates in-memory WebP thumbnails (`_thumbs/360/` q76 and `_thumbs/640/` q80) without committing
    them to Git.
  - Supports `--git-range <before> <after>` (incremental sync on push, including renames/deletes)
    and `--full [--prune] [--force-thumbs]` (manual audit/resync).
- **Workflow:** `.github/workflows/sync-r2.yml` (`Sync Assets to Cloudflare R2`)
  - Automatically runs incrementally on `push` to `main` touching `C-a/**`, `S-u/**`, `P-o/**`,
    `S-e/**`, `Pol/**`.
  - Can also be dispatched manually (`workflow_dispatch`) with `mode: full | full_prune | force_thumbs`.
  - Required GitHub Secrets: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`
    (optional `R2_BUCKET_NAME`, defaults to `sugoi-posters-assets`).
- **Zero-downtime rule:** Always push `Sugoi-Posters-Assets` and let `Sync Assets to Cloudflare R2`
  finish green **before** running `..\SugoiPosters-Web-App\tools\build_web.ps1 -Deploy`.

## Category folder layout (drives everything)

Top-level dirs map to product categories via the `categorias` dict in `productos.py`.
**Only these five prefixes are scanned; any other top-level dir is ignored:**

| Dir   | Category    | Price |
|-------|-------------|-------|
| `C-a` | Camisas     | 280   |
| `S-u` | Sueters     | 500   |
| `P-o` | Posters     | 70    |
| `S-e` | Separadores | 25    |
| `Pol` | Polaroids   | 20    |

Canonical "organized" shape (enforced by `organizar_carpetas.py`):
`Categoria/Subcategoria(serie)/Personaje[_N]/Personaje[_N].webp`. A folder is
"already organized" when it contains exactly one image whose stem equals the
folder name and no subfolders.

`productos.py` handles several shapes per category and these are load-bearing:
- **Personalized products**: subfolders starting with `1_` or containing `personaliz`
  are emitted first and as a single `"Camisa Personalizada #1"`-style product whose
  `imagenes` list bundles *all* images in that folder.
- **C-a/S-u/P-o/Pol**: inner variant folders → `"Nombre Personaje #N"`; loose files
  directly under a subcategory → product per file. For `Pol/anime`, the cleaned
  filename becomes the `subcategoria`.
- **S-e and others**: handled by the generic branch at the bottom of the loop.

## products.dart is generated — never hand-edit it

`products.dart` is overwritten wholesale by `productos.py` and auto-copied to
`../SugoiPosters-Web-App/lib/data/products.dart`. The one piece of state worth preserving across
regenerations is **`dateAdded`**: `productos.py` reads the previous `products.dart` (matching both
exact product names and ASCII-normalized keys) to keep existing dates; genuinely new products get
`dateAdded` from the newest image mtime.

All generated image URLs use `base_url = "https://img.sugoipostershn.com/"` with percent-encoding
via `construir_url_imagen()` as an ASCII safety net (keeps WhatsApp links free of suspicious-link
warnings). Keep filenames pure ASCII via `Quitar_espacios.py`.

## Naming conventions baked into the generator

These regex helpers in `productos.py` define how folder/file names become product names:
- `limpiar_nombre` — strips extension, turns trailing `_1`/`(1)` into ` #1`.
- `normalize_hashes` — collapses `# #`→`#`, drops stray `#` not followed by a digit.
- `formatear_subcategoria` — Title Cases names but preserves all-caps acronyms (`DC`).
- `extraer_variante` — splits trailing number off a folder name for the `#N` suffix.

`Quitar_espacios.py` normalizes spaces, `#`, and non-ASCII characters (`N°8`→`No_8`, `ō`→`o`,
accents/ñ→ASCII) across the 5 catalog folders. `Renombrar.py` normalizes duplicate separators and
renumbers sibling groups to consecutive `_1.._n`.

## Utility scripts (no side effects on the catalog)

- `estructura.py` — dumps the folder tree to `estructura.txt` and a PNG.
- `buscar_carpetas_una_imagen.py` — lists folders containing exactly one image → `carpetas_con_una_imagen.txt`.
- `Copiar.py` — clones a folder tree's structure (dirs only, no files).

## Dependencies

- `convertir.py` and `estructura.py` need **Pillow** (`pip install Pillow`).
- `sync_r2.py` needs **Pillow** and **boto3** (installed automatically inside GitHub Actions).
- Everything else is stdlib. Target Python 3.10+ (uses `X | None` / `dict[str, str]`).
