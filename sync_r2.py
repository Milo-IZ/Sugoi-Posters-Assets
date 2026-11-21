#!/usr/bin/env python3
"""
sync_r2.py — Sincronización incremental de Sugoi-Posters-Assets hacia Cloudflare R2.
=====================================================================================
Sube los originales (C-a, S-u, P-o, S-e, Pol) y genera/sube automáticamente
miniaturas WebP en `_thumbs/360/` y `_thumbs/640/` en memoria (sin contaminar Git),
con `Cache-Control: public, max-age=31536000, immutable`.

Variables de entorno requeridas (excepto con --dry-run):
  R2_ACCOUNT_ID
  R2_ACCESS_KEY_ID
  R2_SECRET_ACCESS_KEY
  R2_BUCKET_NAME        (por defecto: sugoi-posters-assets)

Modos de uso:
  python sync_r2.py --full [--prune] [--force-thumbs]
  python sync_r2.py --git-range <before_sha> <after_sha>
  python sync_r2.py --full --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import io
import mimetypes
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from PIL import Image, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True

CATEGORY_DIRS = ("C-a", "S-u", "P-o", "S-e", "Pol")
IMAGE_EXTENSIONS = (".webp", ".png", ".jpg", ".jpeg")
THUMB_SPECS: tuple[tuple[int, int], ...] = (
    (360, 76),  # tarjetas catálogo móvil y carrito (~12–18 KB)
    (640, 80),  # tarjetas desktop, carrusel y modal detalle (~30–45 KB)
)
CACHE_CONTROL = "public, max-age=31536000, immutable"
REPO_ROOT = Path(__file__).resolve().parent


def is_catalog_image(rel_posix: str) -> bool:
    parts = rel_posix.split("/")
    if len(parts) < 2 or parts[0] not in CATEGORY_DIRS:
        return False
    return rel_posix.lower().endswith(IMAGE_EXTENSIONS)


def thumb_key(size: int, rel_posix: str) -> str:
    return f"_thumbs/{size}/{rel_posix}"


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def guess_content_type(rel_posix: str) -> str:
    ext = Path(rel_posix).suffix.lower()
    if ext == ".webp":
        return "image/webp"
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    guessed, _ = mimetypes.guess_type(rel_posix)
    return guessed or "application/octet-stream"


def generate_thumb_webp(raw_bytes: bytes, max_size: int, quality: int) -> bytes:
    with Image.open(io.BytesIO(raw_bytes)) as img:
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
        copy = img.copy()
        copy.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        copy.save(out, format="WEBP", quality=quality, method=4)
        return out.getvalue()


def scan_local_catalog_images() -> list[str]:
    found: list[str] = []
    for cat in CATEGORY_DIRS:
        cat_dir = REPO_ROOT / cat
        if not cat_dir.is_dir():
            continue
        for root, _dirs, files in os.walk(cat_dir):
            for fname in files:
                if fname.lower().endswith(IMAGE_EXTENSIONS):
                    full = Path(root) / fname
                    if full.stat().st_size == 0:
                        print(f"⚠️  Archivo vacío omitido: {full.relative_to(REPO_ROOT).as_posix()}")
                        continue
                    found.append(full.relative_to(REPO_ROOT).as_posix())
    found.sort()
    return found


def parse_git_diff_range(before: str, after: str) -> tuple[list[str], list[str]] | None:
    """Devuelve (upserts, deletes) desde `git diff`, o None si conviene full sync."""
    if not before or set(before) == {"0"}:
        return None
    try:
        raw = subprocess.check_output(
            ["git", "-c", "core.quotepath=false", "diff", "--name-status", "-z", before, after],
            cwd=REPO_ROOT,
        )
    except subprocess.CalledProcessError as exc:
        print(f"⚠️  No se pudo calcular git diff ({exc}); cambiando a sincronización completa.")
        return None

    tokens = raw.decode("utf-8").split("\x00")
    upserts: set[str] = set()
    deletes: set[str] = set()
    i = 0
    while i < len(tokens):
        status = tokens[i]
        i += 1
        if not status:
            continue
        code = status[0]
        if code in ("R", "C"):
            if i + 1 >= len(tokens):
                break
            old_path = tokens[i]
            new_path = tokens[i + 1]
            i += 2
            if code == "R" and is_catalog_image(old_path):
                deletes.add(old_path)
            if is_catalog_image(new_path):
                upserts.add(new_path)
        else:
            if i >= len(tokens):
                break
            path = tokens[i]
            i += 1
            if not is_catalog_image(path):
                continue
            if code == "D":
                deletes.add(path)
            else:
                upserts.add(path)

    # Si un archivo aparece en ambos sets, prevalece el upsert.
    deletes -= upserts
    return sorted(upserts), sorted(deletes)


def build_r2_client():
    import boto3
    from botocore.config import Config

    account_id = os.environ.get("R2_ACCOUNT_ID", "").strip()
    access_key = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    if not (account_id and access_key and secret_key):
        raise SystemExit(
            "❌ Faltan variables de entorno requeridas: "
            "R2_ACCOUNT_ID, R2_ACCESS_KEY_ID y R2_SECRET_ACCESS_KEY."
        )

    config_kwargs = {
        "signature_version": "s3v4",
        "retries": {"max_attempts": 5, "mode": "standard"},
        "max_pool_connections": 32,
    }
    try:
        cfg = Config(
            **config_kwargs,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
    except TypeError:
        cfg = Config(**config_kwargs)

    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=cfg,
    )


def list_remote_objects(s3, bucket: str) -> dict[str, str]:
    """Devuelve {key: etag_sin_comillas} de todos los objetos actuales del bucket."""
    remote: dict[str, str] = {}
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            remote[obj["Key"]] = obj.get("ETag", "").strip('"')
    return remote


def upload_one_image(
    s3,
    bucket: str,
    rel_posix: str,
    remote_etags: dict[str, str] | None,
    *,
    force_thumbs: bool,
    dry_run: bool,
) -> tuple[int, int, int]:
    """
    Procesa 1 imagen: sube original + miniaturas necesarias.
    Retorna (originals_uploaded, thumbs_uploaded, skipped).
    """
    local_path = REPO_ROOT / rel_posix
    if not local_path.is_file():
        return (0, 0, 1)
    raw = local_path.read_bytes()
    if not raw:
        return (0, 0, 1)

    orig_uploaded = 0
    thumbs_uploaded = 0
    skipped = 0

    local_md5 = md5_bytes(raw)
    orig_changed = remote_etags is None or remote_etags.get(rel_posix) != local_md5

    if orig_changed:
        if not dry_run:
            s3.put_object(
                Bucket=bucket,
                Key=rel_posix,
                Body=raw,
                ContentType=guess_content_type(rel_posix),
                CacheControl=CACHE_CONTROL,
            )
        orig_uploaded += 1
    else:
        skipped += 1

    for size, quality in THUMB_SPECS:
        t_key = thumb_key(size, rel_posix)
        need_thumb = (
            force_thumbs
            or orig_changed
            or remote_etags is None
            or t_key not in remote_etags
        )
        if not need_thumb:
            skipped += 1
            continue

        thumb_bytes = generate_thumb_webp(raw, size, quality)
        if not dry_run:
            s3.put_object(
                Bucket=bucket,
                Key=t_key,
                Body=thumb_bytes,
                ContentType="image/webp",
                CacheControl=CACHE_CONTROL,
            )
        thumbs_uploaded += 1

    return (orig_uploaded, thumbs_uploaded, skipped)


def delete_keys(s3, bucket: str, keys: list[str], *, dry_run: bool) -> int:
    if not keys:
        return 0
    if dry_run:
        return len(keys)
    deleted = 0
    for i in range(0, len(keys), 1000):
        chunk = [{"Key": k} for k in keys[i : i + 1000]]
        s3.delete_objects(Bucket=bucket, Delete={"Objects": chunk, "Quiet": True})
        deleted += len(chunk)
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description="Sincroniza catálogo de imágenes a Cloudflare R2")
    parser.add_argument("--full", action="store_true", help="Escanea todas las categorías y sincroniza faltantes/cambios")
    parser.add_argument("--git-range", nargs=2, metavar=("BEFORE", "AFTER"), help="Sincroniza solo cambios de un rango git")
    parser.add_argument("--prune", action="store_true", help="Elimina de R2 objetos huérfanos que ya no existen en el repo (solo con --full)")
    parser.add_argument("--force-thumbs", action="store_true", help="Regenera y resube miniaturas aunque ya existan en R2")
    parser.add_argument("--workers", type=int, default=16, help="Hilos paralelos de subida (por defecto: 16)")
    parser.add_argument("--dry-run", action="store_true", help="Simula sin escribir ni borrar en R2")
    args = parser.parse_args()

    bucket = os.environ.get("R2_BUCKET_NAME", "sugoi-posters-assets").strip() or "sugoi-posters-assets"

    upserts: list[str] = []
    deletes: list[str] = []
    use_full = args.full

    if args.git_range and not use_full:
        diff_res = parse_git_diff_range(args.git_range[0], args.git_range[1])
        if diff_res is None:
            use_full = True
        else:
            upserts, deletes = diff_res
    elif not use_full:
        use_full = True

    if use_full:
        upserts = scan_local_catalog_images()

    print(
        f"🚀 Modo: {'FULL' if use_full else 'INCREMENTAL'} | "
        f"Bucket: {bucket} | Imágenes a evaluar: {len(upserts)} | Eliminaciones: {len(deletes)}"
        + (" [DRY-RUN]" if args.dry_run else ""),
        flush=True,
    )

    if not upserts and not deletes and not (use_full and args.prune):
        print("✅ Sin cambios de imágenes que sincronizar.")
        return 0

    s3 = None if args.dry_run else build_r2_client()
    remote_etags: dict[str, str] | None = None
    if use_full and not args.dry_run:
        print("📋 Listando objetos actuales en R2...")
        remote_etags = list_remote_objects(s3, bucket)
        print(f"   Objetos actuales en R2: {len(remote_etags)}")

    total_orig = 0
    total_thumbs = 0
    total_skipped = 0
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(
                upload_one_image,
                s3,
                bucket,
                rel,
                remote_etags,
                force_thumbs=args.force_thumbs,
                dry_run=args.dry_run,
            ): rel
            for rel in upserts
        }
        processed = 0
        for fut in as_completed(futures):
            rel = futures[fut]
            processed += 1
            try:
                o, t, s = fut.result()
                total_orig += o
                total_thumbs += t
                total_skipped += s
            except Exception as exc:
                errors.append(f"{rel}: {exc}")
            if processed % 100 == 0 or processed == len(upserts):
                print(
                    f"   Progreso: {processed}/{len(upserts)} "
                    f"(orig +{total_orig}, thumbs +{total_thumbs}, sin cambios {total_skipped})",
                    flush=True,
                )

    keys_to_delete: list[str] = []
    if deletes:
        for rel in deletes:
            keys_to_delete.append(rel)
            for size, _ in THUMB_SPECS:
                keys_to_delete.append(thumb_key(size, rel))
    elif use_full and args.prune and remote_etags is not None:
        expected: set[str] = set()
        for rel in upserts:
            expected.add(rel)
            for size, _ in THUMB_SPECS:
                expected.add(thumb_key(size, rel))
        for remote_key in remote_etags:
            is_managed_orig = is_catalog_image(remote_key)
            is_managed_thumb = remote_key.startswith("_thumbs/")
            if (is_managed_orig or is_managed_thumb) and remote_key not in expected:
                keys_to_delete.append(remote_key)

    deleted_count = delete_keys(s3, bucket, keys_to_delete, dry_run=args.dry_run)

    print(
        f"✅ Sincronización finalizada: originales={total_orig}, "
        f"miniaturas={total_thumbs}, omitidos={total_skipped}, eliminados={deleted_count}"
    )
    if errors:
        print(f"❌ Errores ({len(errors)}):", file=sys.stderr)
        for err in errors[:20]:
            print(f"   - {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
