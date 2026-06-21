#!/usr/bin/env python3
"""
comprimir.py — PNG/JPG/JPEG/WebP → WebP (85% calidad)
=======================================================
Convierte imágenes (PNG, JPG, JPEG, WebP) a WebP con calidad 85%.
- Mantiene un caché (.comprimir_cache.json) para saltar archivos ya procesados.
- Solo procesa imágenes nuevas o modificadas desde la última corrida.
- Los archivos .webp existentes se recomprimen si cambiaron (ej: re-exportados).
- El archivo original se elimina tras la conversión exitosa (solo PNG/JPG/JPEG).
- El nuevo .webp queda en la misma carpeta con el mismo nombre base.
- Recorre todos los subdirectorios recursivamente.

Uso:
    python comprimir.py                  # directorio actual
    python comprimir.py ruta/carpeta     # carpeta específica
    python comprimir.py --calidad 90     # cambiar calidad (default: 85)
    python comprimir.py --dry-run        # simular sin tocar nada
    python comprimir.py --backup         # guardar originales antes
    python comprimir.py --forzar         # ignorar caché, reprocesar todo
"""

import sys
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime

try:
    from PIL import Image, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True
except ImportError:
    print("❌ Pillow no está instalado. Ejecuta: pip install Pillow")
    sys.exit(1)


CACHE_FILE = ".comprimir_cache.json"


# ─── Utilidades ────────────────────────────────────────────────────────────────

def fmt(b: int) -> str:
    for u in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} GB"

def icono(pct: float) -> str:
    if pct >= 70: return "🚀"
    if pct >= 50: return "✅"
    if pct >= 30: return "📉"
    if pct >  0:  return "🔹"
    return "⚠️ "


# ─── Caché ─────────────────────────────────────────────────────────────────────

def cargar_cache(raiz: Path) -> dict:
    """Lee el caché del directorio raíz. Devuelve {} si no existe o está corrupto."""
    cache_path = raiz / CACHE_FILE
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

def guardar_cache(raiz: Path, cache: dict) -> None:
    cache_path = raiz / CACHE_FILE
    cache_path.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

def clave_cache(ruta: Path, raiz: Path) -> str:
    """Clave relativa al raíz para guardar en el caché."""
    # Siempre guardamos la clave como la ruta WebP de salida
    return str(ruta.with_suffix(".webp").relative_to(raiz))

def snapshot(ruta: Path) -> dict:
    """Tamaño + mtime del archivo. Sirve para detectar cambios."""
    st = ruta.stat()
    return {"size": st.st_size, "mtime": round(st.st_mtime, 3)}

def ya_procesado(ruta: Path, raiz: Path, cache: dict) -> bool:
    """
    Devuelve True si el archivo de salida (.webp) ya está en caché
    y su estado en disco coincide con lo que guardamos.
    """
    key = clave_cache(ruta, raiz)
    if key not in cache:
        return False

    # El archivo de salida es siempre el .webp
    webp_path = ruta.with_suffix(".webp")
    if not webp_path.exists():
        return False  # El webp desapareció, hay que regenerarlo

    return snapshot(webp_path) == cache[key]


# ─── Conversión ────────────────────────────────────────────────────────────────

def convertir(ruta: Path, calidad: int, backup_dir: Path | None, dry_run: bool) -> dict:
    res = {
        "tam_orig": ruta.stat().st_size,
        "tam_nuevo": 0,
        "webp_path": ruta.with_suffix(".webp"),
        "error": None,
    }

    try:
        with Image.open(ruta) as img:
            img.load()

            modo = img.mode
            if modo == "P":
                img = img.convert("RGBA" if "transparency" in img.info else "RGB")
            elif modo not in ("RGB", "RGBA", "L", "LA"):
                img = img.convert("RGB")

            if dry_run:
                from io import BytesIO
                buf = BytesIO()
                img.save(buf, format="WEBP", quality=calidad, method=6)
                res["tam_nuevo"] = len(buf.getvalue())
                return res

            if backup_dir:
                dest = backup_dir / ruta.relative_to(ruta.anchor)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ruta, dest)

            webp_path = ruta.with_suffix(".webp")
            img.save(webp_path, format="WEBP", quality=calidad, method=6)
            res["tam_nuevo"] = webp_path.stat().st_size

            # Eliminar original solo si la extensión cambió (PNG/JPG → WebP)
            if ruta != webp_path:
                ruta.unlink()

    except Exception as e:
        res["error"] = str(e)

    return res


# ─── Búsqueda ──────────────────────────────────────────────────────────────────

def buscar_imagenes(directorio: Path, excluir: Path | None = None) -> list[Path]:
    imgs = []
    patrones = (
        "*.png", "*.PNG",
        "*.jpg", "*.jpeg", "*.JPG", "*.JPEG",
        "*.webp", "*.WEBP",
    )
    for ext in patrones:
        imgs.extend(directorio.rglob(ext))

    imgs = sorted(set(imgs))
    if excluir:
        imgs = [i for i in imgs if excluir not in i.parents]
    return imgs


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convierte PNG/JPG/JPEG/WebP a WebP con calidad 85% recursivamente.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "directorio", nargs="?", default=".",
        help="Directorio raíz (default: directorio actual)"
    )
    parser.add_argument(
        "--calidad", type=int, default=85,
        help="Calidad WebP 1-100 (default: 85)"
    )
    parser.add_argument(
        "--backup", action="store_true",
        help="Guardar imágenes originales en _backup_imagenes/ antes de convertir"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Simular sin modificar ningún archivo"
    )
    parser.add_argument(
        "--forzar", action="store_true",
        help="Ignorar caché y reprocesar todas las imágenes"
    )
    args = parser.parse_args()

    raiz = Path(args.directorio).resolve()
    if not raiz.exists() or not raiz.is_dir():
        print(f"❌ Directorio no válido: {raiz}")
        sys.exit(1)

    backup_dir = None
    if args.backup:
        backup_dir = raiz / "_backup_imagenes"
        if not args.dry_run:
            backup_dir.mkdir(exist_ok=True)

    cache = {} if args.forzar else cargar_cache(raiz)

    print(f"\n{'═'*60}")
    print(f"   🖼️  Conversor Multiformato → WebP")
    print(f"{'═'*60}")
    print(f"   📁 Directorio  : {raiz}")
    print(f"   🎯 Calidad     : {args.calidad}%")
    print(f"   💾 Backup      : {'Sí → _backup_imagenes/' if args.backup else 'No'}")
    print(f"   🧪 Dry-run     : {'SÍ — sin cambios reales' if args.dry_run else 'No'}")
    print(f"   ⚡ Caché       : {'Ignorado (--forzar)' if args.forzar else f'{len(cache)} archivos registrados'}")
    print(f"{'═'*60}\n")

    todas = buscar_imagenes(raiz, excluir=backup_dir)

    if not todas:
        print("⚠️  No se encontraron imágenes (PNG, JPG, JPEG o WebP).")
        sys.exit(0)

    # Separar pendientes de ya procesados
    pendientes = [r for r in todas if not ya_procesado(r, raiz, cache)]
    omitidas   = len(todas) - len(pendientes)

    if omitidas:
        print(f"⏭️  {omitidas} imagen(es) sin cambios — omitidas por caché")

    if not pendientes:
        print("✅ Todo está al día. Nada nuevo que procesar.\n")
        sys.exit(0)

    print(f"📸 {len(pendientes)} imagen(es) nuevas o modificadas para procesar\n")

    total_orig = total_nuevo = procesadas = errores = 0
    inicio = datetime.now()

    for n, ruta in enumerate(pendientes, 1):
        rel = ruta.relative_to(raiz)
        es_webp = ruta.suffix.lower() == ".webp"
        etiqueta = " [recompresión]" if es_webp else ""
        print(f"   [{n:>4}/{len(pendientes)}] {rel}{etiqueta}", end=" ... ", flush=True)

        res = convertir(ruta, args.calidad, backup_dir, args.dry_run)
        total_orig += res["tam_orig"]

        if res["error"]:
            print(f"❌ {res['error']}")
            errores += 1
            total_nuevo += res["tam_orig"]
            continue

        pct = (res["tam_orig"] - res["tam_nuevo"]) / res["tam_orig"] * 100
        tag = " [estimado]" if args.dry_run else (" [in-place]" if es_webp else f" → {res['webp_path'].name}")
        print(f"{icono(pct)} {fmt(res['tam_orig'])} → {fmt(res['tam_nuevo'])}  (-{pct:.1f}%){tag}")
        total_nuevo += res["tam_nuevo"]
        procesadas += 1

        # Actualizar caché (solo si no es dry-run)
        if not args.dry_run:
            key = clave_cache(ruta, raiz)
            cache[key] = snapshot(res["webp_path"])
            guardar_cache(raiz, cache)

    elapsed = (datetime.now() - inicio).total_seconds()
    ahorro = total_orig - total_nuevo
    pct_total = (ahorro / total_orig * 100) if total_orig else 0

    print(f"\n{'═'*60}")
    print(f"   📊 RESUMEN {'[DRY-RUN]' if args.dry_run else 'FINAL'}")
    print(f"{'═'*60}")
    print(f"   ✅ Procesadas  : {procesadas}")
    print(f"   ⏭️  Omitidas    : {omitidas} (sin cambios)")
    print(f"   ❌ Errores     : {errores}")
    print(f"   ⏱️  Tiempo      : {elapsed:.1f}s")
    print(f"   📦 Antes       : {fmt(total_orig)}")
    print(f"   📦 Después     : {fmt(total_nuevo)}")
    print(f"   💾 Ahorro      : {fmt(ahorro)}  ({pct_total:.1f}%)")
    if backup_dir and not args.dry_run:
        print(f"   🗂️  Originales  : {backup_dir}")
    print(f"{'═'*60}\n")

    if not args.dry_run and procesadas > 0:
        print("🎉 ¡Listo! Recuerda actualizar las referencias de tus imágenes a .webp\n")


if __name__ == "__main__":
    main()