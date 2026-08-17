#!/usr/bin/env python3
"""
convertir.py — Conversor interactivo y avanzado de imágenes (PNG 100% / WebP)
=============================================================================
Permite convertir colecciones de imágenes (PNG, JPG, JPEG, WebP, BMP, TIFF) a:
  1. PNG con 100% de calidad (sin pérdidas / máxima calidad).
  2. WebP con calidad configurable (85% balanceado, 100% máxima calidad o personalizada).

Características:
  - Ventana gráfica del Explorador de Windows para buscar y elegir cualquier carpeta en el equipo.
  - Modo interactivo con menú para elegir directorios, categorías locales o rutas externas.
  - Modo CLI para scripts automatizados o integración desatendida.
  - Caché inteligente (.comprimir_cache.json) para procesar solo imágenes modificadas/nuevas.
  - Opción de backup automático en _backup_imagenes/.
  - Opción de eliminar archivos originales tras conversión exitosa entre formatos distintos.
  - Soporte completo para transparencias (RGBA), paletas (P) y modos de color complejos.
  - Simulación (dry-run) y reporte detallado de espacio/ahorro.
"""

import os
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
    print("❌ Pillow no está instalado. Ejecuta: pip install Pillow")
    sys.exit(1)


CACHE_FILE = ".comprimir_cache.json"
EXTENSIONES_SOPORTADAS = {
    "*.png", "*.PNG",
    "*.jpg", "*.jpeg", "*.JPG", "*.JPEG",
    "*.webp", "*.WEBP",
    "*.bmp", "*.BMP",
    "*.tiff", "*.TIFF",
}
CARPETAS_IGNORADAS = {".git", "__pycache__", "_backup_imagenes", ".dart_tool", "build", "node_modules"}


# ─── Utilidades de formato ─────────────────────────────────────────────────────

def fmt(b: int) -> str:
    """Convierte bytes a formato legible (KB, MB, GB)."""
    for u in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} GB"

def icono(pct: float) -> str:
    """Devuelve un emoji según el porcentaje de reducción/cambio de tamaño."""
    if pct >= 70: return "🚀"
    if pct >= 50: return "✅"
    if pct >= 30: return "📉"
    if pct >  0:  return "🔹"
    if pct == 0:  return "⚖️ "
    return "📈"  # Crecimiento de tamaño (normal al convertir WebP comprimido a PNG 100%)


# ─── Explorador Gráfico de Carpetas (GUI) ──────────────────────────────────────

def abrir_explorador_gui(
    titulo: str = "Selecciona la carpeta con imágenes a convertir",
    dir_inicial: Path | None = None
) -> Path | None:
    """
    Abre la ventana nativa del Explorador de Archivos de Windows
    para que el usuario seleccione cualquier carpeta del sistema (dentro o fuera de la raíz).
    """
    print("\n🗔 Abriendo el Explorador de Archivos de Windows...")
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.focus_force()

        init_dir = str(dir_inicial) if dir_inicial and dir_inicial.exists() else str(Path.cwd())
        carpeta_seleccionada = filedialog.askdirectory(
            title=titulo,
            initialdir=init_dir
        )
        root.destroy()

        if carpeta_seleccionada:
            p = Path(carpeta_seleccionada).resolve()
            if p.exists() and p.is_dir():
                print(f"✅ Carpeta seleccionada: {p}")
                return p
        print("⚠️ No se seleccionó ninguna carpeta en el explorador.")
    except Exception as e:
        print(f"⚠️ No se pudo abrir la ventana del explorador: {e}")
    return None


# ─── Gestión de Caché ──────────────────────────────────────────────────────────

def cargar_cache(raiz: Path) -> dict:
    """Lee el archivo de caché si existe."""
    cache_path = raiz / CACHE_FILE
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

def guardar_cache(raiz: Path, cache: dict) -> None:
    """Guarda el archivo de caché."""
    cache_path = raiz / CACHE_FILE
    try:
        cache_path.write_text(
            json.dumps(cache, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass

def clave_cache(ruta_salida: Path, raiz: Path) -> str:
    """Genera la clave relativa para el archivo de salida."""
    try:
        return str(ruta_salida.relative_to(raiz))
    except ValueError:
        return str(ruta_salida)

def snapshot(ruta: Path) -> dict:
    """Obtiene el tamaño y mtime de un archivo."""
    st = ruta.stat()
    return {"size": st.st_size, "mtime": round(st.st_mtime, 3)}

def ya_procesado(ruta_origen: Path, ruta_destino: Path, raiz: Path, cache: dict) -> bool:
    """Comprueba si el archivo de salida ya está registrado y sin cambios."""
    if not ruta_destino.exists():
        return False
    key = clave_cache(ruta_destino, raiz)
    if key not in cache:
        return False
    return snapshot(ruta_destino) == cache[key]


# ─── Conversión de Imagen ──────────────────────────────────────────────────────

def convertir_imagen(
    ruta: Path,
    formato_destino: str,
    calidad: int,
    backup_dir: Path | None,
    eliminar_original: bool,
    dry_run: bool
) -> dict:
    """
    Convierte una imagen al formato y calidad deseados.
    formato_destino: 'png' o 'webp'
    """
    ext_destino = f".{formato_destino.lower()}"
    ruta_salida = ruta.with_suffix(ext_destino)
    mismo_archivo = (ruta.resolve() == ruta_salida.resolve())

    res = {
        "tam_orig": ruta.stat().st_size,
        "tam_nuevo": 0,
        "ruta_salida": ruta_salida,
        "mismo_archivo": mismo_archivo,
        "error": None,
    }

    try:
        with Image.open(ruta) as img:
            img.load()

            # Normalizar modos de color para preservar transparencia o RGB limpio
            modo = img.mode
            if formato_destino.lower() == "png":
                if modo == "P":
                    img = img.convert("RGBA" if "transparency" in img.info else "RGB")
                elif modo not in ("RGB", "RGBA", "L", "LA"):
                    img = img.convert("RGBA" if "A" in modo else "RGB")
            else:  # webp
                if modo == "P":
                    img = img.convert("RGBA" if "transparency" in img.info else "RGB")
                elif modo not in ("RGB", "RGBA", "L", "LA"):
                    img = img.convert("RGB")

            # Modo simulación (Dry-Run)
            if dry_run:
                from io import BytesIO
                buf = BytesIO()
                if formato_destino.lower() == "png":
                    img.save(buf, format="PNG", optimize=True, compress_level=6)
                else:
                    if calidad >= 100:
                        img.save(buf, format="WEBP", quality=100, method=6, lossless=True)
                    else:
                        img.save(buf, format="WEBP", quality=calidad, method=6)
                res["tam_nuevo"] = len(buf.getvalue())
                return res

            # Realizar backup si está configurado
            if backup_dir:
                try:
                    rel_backup = ruta.relative_to(backup_dir.parent)
                except ValueError:
                    rel_backup = ruta.name
                dest_backup = backup_dir / rel_backup
                dest_backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ruta, dest_backup)

            # Guardar en el formato destino
            if formato_destino.lower() == "png":
                # PNG 100% Calidad (sin pérdidas)
                img.save(ruta_salida, format="PNG", optimize=True, compress_level=6)
            else:
                # WebP
                if calidad >= 100:
                    img.save(ruta_salida, format="WEBP", quality=100, method=6, lossless=True)
                else:
                    img.save(ruta_salida, format="WEBP", quality=calidad, method=6)

            res["tam_nuevo"] = ruta_salida.stat().st_size

            # Eliminar original si cambió de extensión y está habilitada la opción
            if eliminar_original and not mismo_archivo and ruta.exists():
                ruta.unlink()

    except Exception as e:
        res["error"] = str(e)

    return res


# ─── Búsqueda de Archivos ──────────────────────────────────────────────────────

def buscar_imagenes(directorio: Path, excluir: Path | None = None) -> list[Path]:
    """Busca todas las imágenes en el directorio recursivamente."""
    imgs = []
    for pat in EXTENSIONES_SOPORTADAS:
        for p in directorio.rglob(pat):
            if any(ign in p.parts for ign in CARPETAS_IGNORADAS):
                continue
            if excluir and (excluir == p or excluir in p.parents):
                continue
            imgs.append(p)
    return sorted(set(imgs))


# ─── Interfaz Interactiva ──────────────────────────────────────────────────────

def obtener_carpetas_principales(raiz: Path) -> list[Path]:
    """Obtiene las subcarpetas de primer nivel válidas en el proyecto."""
    carpetas = []
    for p in raiz.iterdir():
        if p.is_dir() and p.name not in CARPETAS_IGNORADAS and not p.name.startswith("."):
            carpetas.append(p)
    return sorted(carpetas, key=lambda x: x.name.lower())

def seleccionar_directorio_interactivo(raiz: Path) -> Path:
    """Muestra un menú claro para que el usuario elija qué carpeta procesar."""
    carpetas = obtener_carpetas_principales(raiz)

    while True:
        print("\n" + "=" * 65)
        print(" 📂 SELECCIÓN DE DIRECTORIO A PROCESAR")
        print("=" * 65)
        print(f" Raíz de referencia: {raiz}")
        print("-" * 65)
        print("  E. 🗔 ABRIR EXPLORADOR DE WINDOWS (Examinar carpetas fuera de la raíz)")
        print("-" * 65)
        print("  0. Todo el proyecto local (Raíz completa)")
        for i, c in enumerate(carpetas, start=1):
            num_imgs = len(buscar_imagenes(c))
            print(f"  {i:>2}. {c.name:<25} ({num_imgs} imágenes)")
        print("-" * 65)
        print("  S. Explorar y elegir una subcarpeta específica del proyecto")
        print("  R. Escribir ruta manual / pegar desde el portapapeles")
        print("=" * 65)

        opc = input("\n👉 Selecciona una opción [E para abrir Explorador / 0 para raíz]: ").strip()
        
        # Opción Explorador Gráfico de Windows
        if opc.lower() in ("e", "explorador", "gui", "examinar"):
            elegida = abrir_explorador_gui(dir_inicial=raiz)
            if elegida:
                return elegida
            print("Intenta nuevamente o elige una opción del menú.")
            continue

        if opc == "0" or opc == "":
            return raiz

        if opc.isdigit():
            idx = int(opc) - 1
            if 0 <= idx < len(carpetas):
                return carpetas[idx]
            print("❌ Número fuera de rango.")
            continue
        
        if opc.lower() == "s":
            print("\nCarpetas locales disponibles:")
            for i, c in enumerate(carpetas, start=1):
                print(f"  {i}. {c.name}")
            sub_opc = input("¿Qué carpeta deseas explorar?: ").strip()
            if sub_opc.isdigit() and 1 <= int(sub_opc) <= len(carpetas):
                elegida = carpetas[int(sub_opc) - 1]
                subdirs = [p for p in elegida.iterdir() if p.is_dir() and not p.name.startswith(".")]
                if not subdirs:
                    print(f"⚠️  No hay subcarpetas dentro de {elegida.name}. Usando {elegida.name}.")
                    return elegida
                print(f"\nSubcarpetas en {elegida.name}:")
                for j, s in enumerate(subdirs, start=1):
                    imgs_s = len(buscar_imagenes(s))
                    print(f"  {j:>2}. {s.name:<30} ({imgs_s} imágenes)")
                sub_sel = input("\nElige la subcarpeta: ").strip()
                if sub_sel.isdigit() and 1 <= int(sub_sel) <= len(subdirs):
                    return subdirs[int(sub_sel) - 1]
            print("⚠️  Opción no válida. Regresando...")
            continue

        if opc.lower() == "r":
            ruta_str = input("👉 Introduce la ruta (absoluta o relativa): ").strip().strip('"').strip("'")
            p = Path(ruta_str)
            if not p.is_absolute():
                p = (raiz / p).resolve()
            if p.exists() and p.is_dir():
                return p
            print(f"❌ La ruta no existe o no es un directorio: {p}")
            continue

        print("❌ Opción inválida. Intenta nuevamente.")

def seleccionar_formato_interactivo() -> tuple[str, int]:
    """Pregunta el formato y calidad deseados."""
    print("\n" + "=" * 65)
    print(" 🎨 FORMATO DE CONVERSIÓN")
    print("=" * 65)
    print("  1. PNG  - 100% Calidad (Sin pérdidas / Lossless)")
    print("  2. WebP - 85% Calidad (Recomendado para web / catálogo)")
    print("  3. WebP - 100% Calidad (Máxima fidelidad WebP / Lossless)")
    print("  4. WebP - Calidad personalizada (1 - 100%)")
    print("=" * 65)

    while True:
        opc = input("\n👉 Elige el formato deseado [1-4, default: 2]: ").strip()
        if opc == "1":
            return "png", 100
        elif opc == "2" or opc == "":
            return "webp", 85
        elif opc == "3":
            return "webp", 100
        elif opc == "4":
            while True:
                q_str = input("Introduce el % de calidad WebP (1-100) [85]: ").strip()
                if not q_str:
                    return "webp", 85
                if q_str.isdigit() and 1 <= int(q_str) <= 100:
                    return "webp", int(q_str)
                print("❌ Por favor introduce un número entre 1 y 100.")
        print("❌ Opción no válida.")

def preguntar_opciones_adicionales() -> tuple[bool, bool]:
    """Pregunta por backup y eliminación de originales."""
    print("\n" + "=" * 65)
    print(" ⚙️  CONFIGURACIÓN ADICIONAL")
    print("=" * 65)
    
    resp_backup = input("¿Deseas crear una copia de respaldo antes de procesar? (s/N) [N]: ").strip().lower()
    hacer_backup = (resp_backup == "s")

    resp_eliminar = input("¿Deseas eliminar los archivos originales tras convertirlos a otro formato? (S/n) [S]: ").strip().lower()
    eliminar_orig = (resp_eliminar != "n")

    return hacer_backup, eliminar_orig


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convierte imágenes a PNG (100%% calidad) o WebP de forma interactiva o por CLI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "directorio", nargs="?", default=None,
        help="Directorio a procesar (omite para modo interactivo con menú)"
    )
    parser.add_argument(
        "-e", "--explorador", action="store_true",
        help="Abrir directamente la ventana gráfica del Explorador de Windows para elegir carpeta"
    )
    parser.add_argument(
        "--formato", choices=["png", "PNG", "webp", "WEBP"], default=None,
        help="Formato de salida: 'png' (100%% calidad) o 'webp'"
    )
    parser.add_argument(
        "--calidad", type=int, default=None,
        help="Calidad de salida (1-100). Default: 100 para PNG, 85 para WebP"
    )
    parser.add_argument(
        "--backup", action="store_true",
        help="Guardar copia de seguridad en _backup_imagenes/ antes de convertir"
    )
    parser.add_argument(
        "--eliminar-originales", action="store_true", default=None,
        help="Eliminar archivos originales al cambiar de formato"
    )
    parser.add_argument(
        "--no-eliminar", action="store_true",
        help="Conservar los archivos originales tras la conversión"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Simular sin modificar ningún archivo en disco"
    )
    parser.add_argument(
        "--forzar", action="store_true",
        help="Ignorar caché y procesar todas las imágenes"
    )
    parser.add_argument(
        "-i", "--interactivo", action="store_true",
        help="Forzar menú interactivo paso a paso"
    )

    args = parser.parse_args()
    raiz_proyecto = Path.cwd().resolve()

    # Si se solicitó abrir directamente el explorador
    if args.explorador:
        dir_seleccionado = abrir_explorador_gui(dir_inicial=raiz_proyecto)
        if not dir_seleccionado:
            print("❌ Operación cancelada por el usuario.")
            sys.exit(0)
        formato_destino, calidad = seleccionar_formato_interactivo()
        hacer_backup, eliminar_original = preguntar_opciones_adicionales()
        dry_run = False
        forzar = False
    elif args.interactivo or (args.directorio is None and args.formato is None):
        print("\n" + "=" * 65)
        print("   🖼️  CONVERSOR DE IMÁGENES — SUGOI ASSETS")
        print("       (PNG 100% Calidad / WebP)")
        print("=" * 65)

        dir_seleccionado = seleccionar_directorio_interactivo(raiz_proyecto)
        formato_destino, calidad = seleccionar_formato_interactivo()
        hacer_backup, eliminar_original = preguntar_opciones_adicionales()
        dry_run = False
        forzar = False
    else:
        # Modo línea de comandos
        dir_seleccionado = Path(args.directorio).resolve() if args.directorio else raiz_proyecto
        formato_destino = (args.formato or "webp").lower()
        if args.calidad is not None:
            calidad = args.calidad
        else:
            calidad = 100 if formato_destino == "png" else 85

        hacer_backup = args.backup
        if args.no_eliminar:
            eliminar_original = False
        elif args.eliminar_originales:
            eliminar_original = True
        else:
            eliminar_original = True  # Por defecto elimina si cambió de extensión

        dry_run = args.dry_run
        forzar = args.forzar

    if not dir_seleccionado.exists() or not dir_seleccionado.is_dir():
        print(f"❌ Directorio no válido: {dir_seleccionado}")
        sys.exit(1)

    backup_dir = None
    if hacer_backup:
        backup_dir = dir_seleccionado / "_backup_imagenes"
        if not dry_run:
            backup_dir.mkdir(parents=True, exist_ok=True)

    cache = {} if forzar else cargar_cache(dir_seleccionado)

    print(f"\n{'='*65}")
    print(f"   🚀 INICIANDO PROCESO DE CONVERSIÓN")
    print(f"{'='*65}")
    print(f"   📁 Directorio       : {dir_seleccionado}")
    print(f"   🎯 Formato Salida   : {formato_destino.upper()}")
    print(f"   💎 Calidad          : {calidad}%{' (Lossless sin pérdidas)' if calidad == 100 else ''}")
    print(f"   💾 Backup           : {'Sí → _backup_imagenes/' if hacer_backup else 'No'}")
    print(f"   🗑️  Eliminar orig.   : {'Sí (al cambiar extensión)' if eliminar_original else 'No'}")
    print(f"   🧪 Dry-run (prueba) : {'SÍ — sin cambios reales' if dry_run else 'No'}")
    print(f"   ⚡ Caché            : {'Ignorado (--forzar)' if forzar else f'{len(cache)} registros'}")
    print(f"{'='*65}\n")

    todas = buscar_imagenes(dir_seleccionado, excluir=backup_dir)

    if not todas:
        print("⚠️  No se encontraron imágenes en el directorio seleccionado.")
        sys.exit(0)

    # Filtrar imágenes pendientes
    pendientes = []
    omitidas = 0
    ext_dest = f".{formato_destino.lower()}"

    for img in todas:
        dest = img.with_suffix(ext_dest)
        if not forzar and ya_procesado(img, dest, dir_seleccionado, cache):
            omitidas += 1
        else:
            pendientes.append(img)

    if omitidas:
        print(f"⏭️  {omitidas} imagen(es) sin cambios — omitidas por caché")

    if not pendientes:
        print("✅ Todo está al día. No hay imágenes nuevas o modificadas que procesar.\n")
        sys.exit(0)

    print(f"📸 {len(pendientes)} imagen(es) listas para procesar...\n")

    total_orig = 0
    total_nuevo = 0
    procesadas = 0
    errores = 0
    inicio = datetime.now()

    for n, ruta in enumerate(pendientes, 1):
        try:
            rel = ruta.relative_to(dir_seleccionado)
        except ValueError:
            rel = ruta.name

        mismo_formato = (ruta.suffix.lower() == ext_dest)
        etiqueta = " [recompresión]" if mismo_formato else f" → {ext_dest.upper()}"
        print(f"   [{n:>4}/{len(pendientes)}] {rel}{etiqueta}", end=" ... ", flush=True)

        res = convertir_imagen(
            ruta=ruta,
            formato_destino=formato_destino,
            calidad=calidad,
            backup_dir=backup_dir,
            eliminar_original=eliminar_original,
            dry_run=dry_run
        )
        total_orig += res["tam_orig"]

        if res["error"]:
            print(f"❌ {res['error']}")
            errores += 1
            total_nuevo += res["tam_orig"]
            continue

        pct = (res["tam_orig"] - res["tam_nuevo"]) / res["tam_orig"] * 100 if res["tam_orig"] > 0 else 0
        tag = " [estimado]" if dry_run else f" → {res['ruta_salida'].name}"
        diff_str = f"(-{pct:.1f}%)" if pct >= 0 else f"(+{abs(pct):.1f}%)"
        print(f"{icono(pct)} {fmt(res['tam_orig'])} → {fmt(res['tam_nuevo'])} {diff_str}{tag}")
        total_nuevo += res["tam_nuevo"]
        procesadas += 1

        # Actualizar caché
        if not dry_run and res["ruta_salida"].exists():
            key = clave_cache(res["ruta_salida"], dir_seleccionado)
            cache[key] = snapshot(res["ruta_salida"])
            guardar_cache(dir_seleccionado, cache)

    elapsed = (datetime.now() - inicio).total_seconds()
    ahorro = total_orig - total_nuevo
    pct_total = (ahorro / total_orig * 100) if total_orig else 0

    print(f"\n{'='*65}")
    print(f"   📊 RESUMEN {'[DRY-RUN]' if dry_run else 'FINAL'}")
    print(f"{'='*65}")
    print(f"   ✅ Procesadas    : {procesadas}")
    print(f"   ⏭️  Omitidas      : {omitidas} (sin cambios)")
    print(f"   ❌ Errores       : {errores}")
    print(f"   ⏱️  Tiempo trans. : {elapsed:.2f}s")
    print(f"   📦 Tamaño Antes  : {fmt(total_orig)}")
    print(f"   📦 Tamaño Nuevo  : {fmt(total_nuevo)}")
    if ahorro >= 0:
        print(f"   💾 Espacio Ahorr : {fmt(ahorro)}  (-{pct_total:.1f}%)")
    else:
        print(f"   💎 Fidelidad Max : +{fmt(abs(ahorro))} (+{abs(pct_total):.1f}%)")
    if backup_dir and not dry_run:
        print(f"   🗂️  Respaldos en  : {backup_dir}")
    print(f"{'='*65}\n")

    if not dry_run and procesadas > 0:
        print("🎉 ¡Conversión finalizada con éxito!\n")


if __name__ == "__main__":
    main()