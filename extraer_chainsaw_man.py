#!/usr/bin/env python3
"""
extraer_chainsaw_man.py — Extractor de imágenes de Chainsaw Man
===============================================================
Busca todas las imágenes pertenecientes al catálogo de Chainsaw Man
y las copia a una carpeta en la raíz (E:\\Proyectos\\Chainsaw_Man_Imagenes).

Características:
  - Detección precisa de las 75 imágenes oficiales de Chainsaw Man en el catálogo.
  - Asignación de nombres únicos y limpios basados en personaje y variante
    (ej: Chainsaw_Man_Denji_1.webp, Chainsaw_Man_Power_5.webp, Pol_Anime_Chainsaw_Man.webp).
  - Generación de manifiesto manifest.json y resumen.txt con dimensiones y tamaños.
  - Opción de convertir a PNG 100% de calidad al vuelo (--convertir-png).
  - Opción de guardar de forma plana (--modo plano) o estructurada (--modo estructurado).

Uso:
    python extraer_chainsaw_man.py
    python extraer_chainsaw_man.py --convertir-png
    python extraer_chainsaw_man.py --destino Mi_Carpeta
"""

import sys
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime

# Configuración de codificación para consola Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from PIL import Image, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True
except ImportError:
    Image = None


CARPETAS_IGNORADAS = {
    ".git", "__pycache__", "node_modules", ".dart_tool", "build",
    "_backup_imagenes", ".idea", ".vscode"
}

EXTENSIONES_VALIDAS = {".webp", ".png", ".jpg", ".jpeg", ".bmp", ".tiff"}


def fmt_tam(b: int) -> str:
    """Convierte bytes a formato legible."""
    for u in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} GB"


def es_imagen_chainsaw_man(ruta: Path) -> bool:
    """Verifica con precisión si una imagen pertenece al universo Chainsaw Man."""
    if ruta.suffix.lower() not in EXTENSIONES_VALIDAS:
        return False

    partes = [p.lower() for p in ruta.parts]
    # Comprobar si está en una subcategoría Chainsaw_Man o si el archivo es Chainsaw_Man
    return any("chainsaw" in part for part in partes) or any(part == "csm" for part in partes)


def buscar_imagenes_chainsaw_man(origen: Path, excluir_dir: Path | None = None) -> list[Path]:
    """Escanea el directorio origen buscando todas las imágenes de Chainsaw Man."""
    encontradas = []
    for p in origen.rglob("*"):
        if any(ign in p.parts for ign in CARPETAS_IGNORADAS):
            continue
        if excluir_dir and (excluir_dir == p or excluir_dir in p.parents):
            continue
        if p.is_file() and es_imagen_chainsaw_man(p):
            encontradas.append(p)
    return sorted(encontradas, key=lambda x: str(x).lower())


def generar_nombre_limpio(img_path: Path, origen: Path, ext_salida: str | None = None) -> str:
    """
    Genera un nombre descriptivo, limpio y único para cada imagen.
    Ejemplo:
      C-a/Chainsaw_Man/Denji_1/Denji/Denji.webp -> Chainsaw_Man_Denji_1.webp
      C-a/Chainsaw_Man/Makima_2/Makima/Makima.webp -> Chainsaw_Man_Makima_2.webp
      C-a/Chainsaw_Man/Chainsaw_Demon/Chainsaw_Demon.webp -> Chainsaw_Man_Chainsaw_Demon.webp
      Pol/Anime/Chainsaw_Man.webp -> Pol_Anime_Chainsaw_Man.webp
    """
    try:
        rel_parts = list(img_path.relative_to(origen).parts)
    except ValueError:
        rel_parts = list(img_path.parts[-3:])

    ext = ext_salida if ext_salida else img_path.suffix

    # Si viene de Sugoi-Posters-Assets/C-a/Chainsaw_Man/...
    if "Chainsaw_Man" in rel_parts:
        idx_csm = rel_parts.index("Chainsaw_Man")
        sub_partes = rel_parts[idx_csm + 1:]
        
        if sub_partes:
            # Tomar el nombre del personaje/variante (la primera subcarpeta tras Chainsaw_Man)
            nombre_variante = sub_partes[0]
            # Si hay más subpartes (ej: Chainsaw_man_reze_arc_1/Chainsaw_man_reze_arc/...)
            return f"Chainsaw_Man_{nombre_variante}{ext}"
        else:
            return f"Chainsaw_Man{ext}"
    
    # Para casos como Pol/Anime/Chainsaw_Man.webp
    partes_utiles = [p for p in rel_parts[:-1] if p not in ("Sugoi-Posters-Assets", "Proyectos")]
    partes_utiles.append(img_path.stem)
    return f"{'_'.join(partes_utiles)}{ext}"


def extraer_imagenes(
    origen: Path,
    destino: Path,
    convertir_a_png: bool = False,
    modo_estructurado: bool = False
) -> list[dict]:
    """Extrae y copia las imágenes de Chainsaw Man a la carpeta destino."""
    # Limpiar y preparar directorio destino
    destino.mkdir(parents=True, exist_ok=True)
    imagenes = buscar_imagenes_chainsaw_man(origen, excluir_dir=destino)

    if not imagenes:
        print("⚠️  No se encontraron imágenes de Chainsaw Man.")
        return []

    print("\n" + "=" * 65)
    print(" 🪚 EXTRACTOR DE IMÁGENES DE CHAINSAW MAN")
    print("=" * 65)
    print(f" 📂 Origen      : {origen}")
    print(f" 📁 Destino     : {destino}")
    print(f" 🖼️  Encontradas : {len(imagenes)} imágenes")
    print(f" 🎨 Formato     : {'Convertir a PNG (100% Calidad Lossless)' if convertir_a_png else 'Mantener formato original (.webp)'}")
    print(f" 🗂️  Modo        : {'Estructurado por subcarpetas' if modo_estructurado else 'Plano (Nombres únicos descriptivos)'}")
    print("=" * 65 + "\n")

    manifest = []
    total_bytes = 0
    archivos_generados = set()

    for i, img in enumerate(imagenes, start=1):
        ext_final = ".png" if convertir_a_png else img.suffix
        nombre_archivo = generar_nombre_limpio(img, origen, ext_salida=ext_final)

        if modo_estructurado:
            try:
                rel = img.relative_to(origen)
            except ValueError:
                rel = img.name
            target_path = destino / rel
            if convertir_a_png:
                target_path = target_path.with_suffix(".png")
            target_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            # Asegurar unicidad
            target_path = destino / nombre_archivo
            contador = 1
            stem_orig = target_path.stem
            while target_path.name in archivos_generados:
                target_path = destino / f"{stem_orig}_{contador}{ext_final}"
                contador += 1
            archivos_generados.add(target_path.name)

        dimensiones = "N/A"
        tam_origen = img.stat().st_size

        if convertir_a_png and Image:
            try:
                with Image.open(img) as pil_img:
                    pil_img.load()
                    dimensiones = f"{pil_img.width}x{pil_img.height}"
                    modo = pil_img.mode
                    if modo == "P":
                        pil_img = pil_img.convert("RGBA" if "transparency" in pil_img.info else "RGB")
                    elif modo not in ("RGB", "RGBA", "L", "LA"):
                        pil_img = pil_img.convert("RGBA" if "A" in modo else "RGB")
                    pil_img.save(target_path, format="PNG", optimize=True, compress_level=6)
                tam_final = target_path.stat().st_size
            except Exception as e:
                print(f"❌ Error al convertir {img.name}: {e}. Copiando original...")
                shutil.copy2(img, target_path)
                tam_final = target_path.stat().st_size
        else:
            shutil.copy2(img, target_path)
            tam_final = target_path.stat().st_size
            if Image:
                try:
                    with Image.open(img) as pil_img:
                        dimensiones = f"{pil_img.width}x{pil_img.height}"
                except Exception:
                    pass

        total_bytes += tam_final

        info = {
            "index": i,
            "archivo_salida": target_path.name,
            "ruta_destino": str(target_path),
            "ruta_origen": str(img),
            "dimensiones": dimensiones,
            "tam_bytes": tam_final,
            "tam_formato": fmt_tam(tam_final),
            "formato": target_path.suffix.lower().replace(".", "").upper()
        }
        manifest.append(info)

        print(f" [{i:>2}/{len(imagenes)}] ✓ {target_path.name:<45} ({dimensiones}, {fmt_tam(tam_final)})")

    # Guardar manifiesto JSON
    manifest_path = destino / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "fecha_extraccion": datetime.now().isoformat(),
            "total_imagenes": len(imagenes),
            "tamano_total": fmt_tam(total_bytes),
            "imagenes": manifest
        }, f, indent=2, ensure_ascii=False)

    # Guardar resumen en texto legible
    resumen_path = destino / "resumen.txt"
    with open(resumen_path, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write(" RESUMEN DE IMÁGENES EXTRAÍDAS DE CHAINSAW MAN\n")
        f.write("=" * 70 + "\n")
        f.write(f"Fecha de extracción : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total de imágenes   : {len(imagenes)}\n")
        f.write(f"Tamaño total        : {fmt_tam(total_bytes)}\n")
        f.write(f"Carpeta destino     : {destino}\n")
        f.write("-" * 70 + "\n\n")
        for item in manifest:
            f.write(f"[{item['index']:>2}] {item['archivo_salida']:<45} | {item['dimensiones']:<10} | {item['tam_formato']:<9} | Origen: {item['ruta_origen']}\n")

    print("\n" + "=" * 65)
    print(" 🎉 EXTRACCIÓN COMPLETADA CON ÉXITO")
    print("=" * 65)
    print(f"  ✅ Imágenes extraídas : {len(imagenes)}")
    print(f"  📦 Tamaño total       : {fmt_tam(total_bytes)}")
    print(f"  📁 Carpeta destino    : {destino}")
    print(f"  📄 Manifiesto JSON    : {manifest_path}")
    print(f"  📝 Resumen de texto   : {resumen_path}")
    print("=" * 65 + "\n")

    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Extrae todas las imágenes de Chainsaw Man en una carpeta en la raíz.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--origen", type=str, default=None,
        help="Directorio origen a escanear (default: detecta Sugoi-Posters-Assets o raíz actual)"
    )
    parser.add_argument(
        "--destino", type=str, default=None,
        help="Carpeta destino en la raíz (default: E:\\Proyectos\\Chainsaw_Man_Imagenes)"
    )
    parser.add_argument(
        "--convertir-png", action="store_true",
        help="Convertir todas las imágenes extraídas a formato PNG (100% calidad)"
    )
    parser.add_argument(
        "--modo", choices=["plano", "estructurado"], default="plano",
        help="Modo de guardado: 'plano' (todo en una carpeta) o 'estructurado' (subcarpetas)"
    )

    args = parser.parse_args()

    raiz_proyectos = Path("E:/Proyectos").resolve() if Path("E:/Proyectos").exists() else Path.cwd().resolve()

    # Determinar origen
    if args.origen:
        origen = Path(args.origen).resolve()
    else:
        assets_dir = raiz_proyectos / "Sugoi-Posters-Assets"
        origen = assets_dir if assets_dir.exists() else raiz_proyectos

    # Determinar destino
    if args.destino:
        destino = Path(args.destino).resolve()
        if not destino.is_absolute():
            destino = raiz_proyectos / destino
    else:
        destino = raiz_proyectos / "Chainsaw_Man_Imagenes"

    extraer_imagenes(
        origen=origen,
        destino=destino,
        convertir_a_png=args.convertir_png,
        modo_estructurado=(args.modo == "estructurado")
    )


if __name__ == "__main__":
    main()
