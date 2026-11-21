import argparse
import os
import re
import sys
import unicodedata

# Evitar UnicodeEncodeError con emojis/acentos en consolas Windows (cp1252)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Carpetas raíz del catálogo (nunca toca .git, .github ni scripts)
CATEGORY_DIRS = ("C-a", "S-u", "P-o", "S-e", "Pol")

# Extensiones de imagen que se procesarán
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")


def normalize_segment(name: str, is_file: bool = False) -> str:
    """
    Normaliza un nombre de carpeta o archivo de imagen a ASCII seguro para URLs/R2/WhatsApp:
      - N°8 / Nº8 -> No_8
      - Acentos y diacríticos (ō, á, ñ, etc.) -> ASCII base (o, a, n, etc.)
      - Espacios y '#' -> '_'
      - Elimina cualquier otro carácter no-ASCII restante
    """
    if is_file:
        stem, ext = os.path.splitext(name)
        ext = ext.lower()
    else:
        stem, ext = name, ""

    # Casos comunes tipo "Kaiju_N°8" o "N° 8" -> "Kaiju_No_8" / "No_8"
    stem = re.sub(r"(?<![A-Za-z])([Nn])[°º]\s*(\d+)", r"\1o_\2", stem)
    # Cualquier otro símbolo de grado/ordinal suelto -> "o"
    stem = stem.replace("°", "o").replace("º", "o")

    # Descomponer Unicode y quitar marcas diacríticas (ō -> o, ñ -> n, á -> a)
    stem = unicodedata.normalize("NFKD", stem)
    stem = "".join(ch for ch in stem if not unicodedata.combining(ch))

    # Reemplazar espacios y '#' por '_'
    stem = re.sub(r"[ #]+", "_", stem)

    # Eliminar cualquier carácter no-ASCII restante
    stem = stem.encode("ascii", "ignore").decode("ascii")

    # Evitar guiones bajos duplicados solo al inicio/fin (preserva "__2" interno para Renombrar.py)
    stem = stem.strip("_")

    return f"{stem}{ext}"


def _safe_rename(old_path: str, new_path: str, label: str, dry_run: bool) -> bool:
    if old_path == new_path:
        return False

    same_case_only = old_path.lower() == new_path.lower()
    if os.path.exists(new_path) and not same_case_only:
        print(f"⚠️  {label} saltado (ya existe): {new_path}")
        return False

    prefix = "[DRY-RUN] " if dry_run else ""
    print(f"{prefix}{label} renombrado: {old_path} -> {new_path}")
    if dry_run:
        return True

    if same_case_only:
        tmp_path = old_path + ".__tmp_rename__"
        os.rename(old_path, tmp_path)
        os.rename(tmp_path, new_path)
    else:
        os.rename(old_path, new_path)
    return True


def rename_files_and_folders(root_dir: str, *, dry_run: bool = False) -> tuple[int, int]:
    files_renamed = 0
    dirs_renamed = 0

    for cat in CATEGORY_DIRS:
        cat_path = os.path.join(root_dir, cat)
        if not os.path.isdir(cat_path):
            continue

        # topdown=False para renombrar primero archivos y subcarpetas internas
        for root, dirs, files in os.walk(cat_path, topdown=False):
            for file in files:
                if not file.lower().endswith(IMAGE_EXTENSIONS):
                    continue
                new_name = normalize_segment(file, is_file=True)
                if new_name != file:
                    old_path = os.path.join(root, file)
                    new_path = os.path.join(root, new_name)
                    if _safe_rename(old_path, new_path, "Archivo", dry_run):
                        files_renamed += 1

            for dir_name in dirs:
                new_dir_name = normalize_segment(dir_name, is_file=False)
                if new_dir_name != dir_name:
                    old_dir_path = os.path.join(root, dir_name)
                    new_dir_path = os.path.join(root, new_dir_name)
                    if _safe_rename(old_dir_path, new_dir_path, "Carpeta", dry_run):
                        dirs_renamed += 1

    return files_renamed, dirs_renamed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normaliza espacios, '#' y caracteres no-ASCII en el catálogo de imágenes."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra los renombramientos sin aplicar cambios en disco.",
    )
    args = parser.parse_args()

    root_directory = os.path.dirname(os.path.abspath(__file__))
    files_count, dirs_count = rename_files_and_folders(root_directory, dry_run=args.dry_run)

    if files_count == 0 and dirs_count == 0:
        print("✅ Todos los nombres del catálogo ya están normalizados en ASCII.")
    else:
        modo = "simulados" if args.dry_run else "aplicados"
        print(f"✅ Cambios {modo}: {files_count} archivo(s), {dirs_count} carpeta(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
