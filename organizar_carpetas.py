import os
import shutil
import sys
import time
from pathlib import Path

# Evitar UnicodeEncodeError con emojis en consolas Windows (cp1252)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Extensiones válidas de imagen
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}

# Carpetas del sistema a ignorar
IGNORED_DIR_NAMES = {".git", "__pycache__", ".vscode", ".agents", "build", ".dart_tool"}

DIR_BASE = Path(__file__).resolve().parent


# ==========================
# UTILIDADES
# ==========================

def is_image(file_path: Path) -> bool:
    return file_path.is_file() and file_path.suffix.lower() in IMAGE_EXTENSIONS


def should_ignore_dir(dir_path: Path) -> bool:
    return dir_path.name in IGNORED_DIR_NAMES or dir_path.name.startswith(".")


def get_top_level_folders(root: Path):
    return sorted(
        [p for p in root.iterdir() if p.is_dir() and not should_ignore_dir(p)],
        key=lambda p: p.name.lower()
    )


def get_all_dirs(root: Path):
    """
    Devuelve root + todas sus subcarpetas, excluyendo carpetas ignoradas.
    Se hace una captura fija de la estructura para no interferir mientras movemos archivos.
    """
    dirs = [root]
    for p in root.rglob("*"):
        if p.is_dir() and not should_ignore_dir(p):
            dirs.append(p)
    return sorted(dirs, key=lambda p: (len(p.parts), str(p).lower()))


def direct_images(folder: Path):
    return [f for f in folder.iterdir() if is_image(f)]


def direct_dirs(folder: Path):
    return [d for d in folder.iterdir() if d.is_dir() and not should_ignore_dir(d)]


def unique_file_path(path: Path) -> Path:
    """
    Si ya existe un archivo con ese nombre, agrega _1, _2, etc.
    """
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent

    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def is_already_organized(folder: Path) -> bool:
    """
    Estructura válida canonical:
        Carpeta/
            Carpeta.ext
    """
    images = direct_images(folder)
    subdirs = direct_dirs(folder)

    if len(images) != 1:
        return False

    if subdirs:
        return False

    return images[0].stem == folder.name


# ==========================
# SELECTOR CON EXPLORADOR
# ==========================

def abrir_explorador_carpetas(directorio_inicial: Path | None = None) -> Path | None:
    """
    Abre una ventana nativa del explorador de archivos para elegir una carpeta.
    Pone la ventana al frente de la consola.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        # Asegura que aparezca al frente
        root.attributes("-topmost", True)

        init_dir = str(directorio_inicial) if directorio_inicial and directorio_inicial.exists() else str(DIR_BASE)

        print("\n📂 Abriendo explorador de archivos para seleccionar carpeta...")
        carpeta = filedialog.askdirectory(
            title="Selecciona la carpeta que deseas organizar",
            initialdir=init_dir
        )
        root.destroy()

        if carpeta:
            return Path(carpeta)
        return None
    except Exception as e:
        print(f"⚠️ No se pudo abrir el explorador gráfico: {e}")
        return None


# ==========================
# ANÁLISIS
# ==========================

def analyze_tree(folder: Path):
    print(f"\n=================================")
    print(f"🔍 ANALIZANDO: {folder}")
    print(f"=================================\n")

    all_dirs = get_all_dirs(folder)

    organized = []
    loose_with_images = []
    empty_dirs = []

    for d in all_dirs:
        imgs = direct_images(d)
        subs = direct_dirs(d)

        if imgs and is_already_organized(d):
            organized.append(d)
        elif imgs:
            loose_with_images.append((d, len(imgs), len(subs)))
        else:
            if not subs and d != folder:
                empty_dirs.append(d)

    print(f"✅ Carpetas ya organizadas ({len(organized)}):")
    if organized:
        # Mostrar las primeras 10 si son muchas
        for d in organized[:10]:
            try:
                rel = d.relative_to(folder)
            except Exception:
                rel = d.name
            print(f"  [OK] {rel}")
        if len(organized) > 10:
            print(f"  ... y {len(organized) - 10} más.")
    else:
        print("  Ninguna")

    print(f"\n⚠️  Carpetas con imágenes sueltas por organizar ({len(loose_with_images)}):")
    total_sueltas = sum(count for _, count, _ in loose_with_images)
    if loose_with_images:
        for d, img_count, sub_count in loose_with_images:
            try:
                rel = d.relative_to(folder)
            except Exception:
                rel = d.name
            print(f"  [SUELTAS] {rel} -> {img_count} imagen(es), {sub_count} subcarpeta(s)")
    else:
        print("  Ninguna (¡Todo limpio!)")

    if empty_dirs:
        print(f"\n📁 Carpetas vacías ({len(empty_dirs)}):")
        for d in empty_dirs[:5]:
            try:
                rel = d.relative_to(folder)
            except Exception:
                rel = d.name
            print(f"  [VACÍA] {rel}")
        if len(empty_dirs) > 5:
            print(f"  ... y {len(empty_dirs) - 5} más.")

    return total_sueltas


# ==========================
# ORGANIZACIÓN
# ==========================

def organize_tree(folder: Path):
    """
    Recorre recursivamente toda la carpeta elegida.
    Si encuentra imágenes sueltas en cualquier nivel, crea una subcarpeta
    con el nombre base de la imagen y mueve el archivo allí.
    """
    start = time.time()
    all_dirs = get_all_dirs(folder)

    moved_files = 0
    created_folders = 0
    skipped_organized = 0

    print(f"\n🚀 Organizando árbol en: {folder}\n")

    for current_dir in all_dirs:
        images = direct_images(current_dir)

        if not images:
            continue

        # Si ya está organizada perfectamente (1 imagen cuyo stem coincide con el nombre de la carpeta y sin subcarpetas)
        if is_already_organized(current_dir):
            skipped_organized += 1
            continue

        for img in images:
            # Si el archivo ya está en una carpeta que tiene exactamente su mismo nombre (y es la única imagen)
            if img.stem == current_dir.name and len(images) == 1:
                skipped_organized += 1
                continue

            target_folder = current_dir / img.stem
            if not target_folder.exists():
                target_folder.mkdir(parents=True, exist_ok=True)
                created_folders += 1

            target_file = unique_file_path(target_folder / img.name)

            shutil.move(str(img), str(target_file))
            moved_files += 1

            try:
                rel_src = img.relative_to(folder)
            except Exception:
                rel_src = img.name

            try:
                rel_dst = target_file.relative_to(folder)
            except Exception:
                rel_dst = target_file.name

            print(f"✓ {rel_src} -> {rel_dst}")

    elapsed = round(time.time() - start, 2)

    print("\n=================================")
    print("📊 RESUMEN DE ORGANIZACIÓN")
    print("=================================")
    print(f"Carpeta procesada : {folder}")
    print(f"Carpetas creadas  : {created_folders}")
    print(f"Archivos movidos  : {moved_files}")
    print(f"Ya organizadas    : {skipped_organized}")
    print(f"Tiempo empleado   : {elapsed}s")
    print("=================================\n")


# ==========================
# GESTIÓN DE CARPETA SELECCIONADA
# ==========================

def procesar_carpeta(carpeta: Path):
    """Analiza la carpeta y permite organizarla de inmediato."""
    sueltas = analyze_tree(carpeta)

    if sueltas == 0:
        print("\n✅ Todas las imágenes ya están organizadas en sus respectivas subcarpetas.")
        return

    confirm = input(f"\n¿Deseas organizar las {sueltas} imágenes sueltas en subcarpetas ahora? (S/n): ").strip().lower()
    if confirm in ("", "s", "si", "y", "yes"):
        organize_tree(carpeta)
    else:
        print("❌ Organización cancelada.")


# ==========================
# MENÚ PRINCIPAL
# ==========================

def main():
    print("==========================================")
    print("   ORGANIZADOR DE CARPETAS DE ASSETS")
    print("==========================================")

    # 1. Si se pasa una ruta como argumento por línea de comandos (ej. arrastrar carpeta sobre el script)
    if len(sys.argv) > 1:
        ruta_arg = Path(sys.argv[1].strip('"'))
        if ruta_arg.is_dir():
            print(f"📁 Usando carpeta pasada por argumento: {ruta_arg}")
            procesar_carpeta(ruta_arg)
            return

    # 2. De una vez: abrir el explorador nativo de Windows al inicio
    carpeta_inicial = abrir_explorador_carpetas(DIR_BASE)
    if carpeta_inicial and carpeta_inicial.is_dir():
        print(f"📁 Carpeta elegida: {carpeta_inicial}")
        procesar_carpeta(carpeta_inicial)
    else:
        print("ℹ️ No se seleccionó carpeta en el explorador inicial.")

    # 3. Menú interactivo por si desea hacer más operaciones
    carpeta_actual = carpeta_inicial if (carpeta_inicial and carpeta_inicial.is_dir()) else DIR_BASE

    while True:
        print("\n==========================================")
        print(" OPCIONES")
        print("==========================================")
        print(f"Carpeta actual: {carpeta_actual}")
        print("------------------------------------------")
        print("1. Elegir otra carpeta con el Explorador de Windows 📂")
        print("2. Organizar la carpeta actual")
        print("3. Analizar la carpeta actual")
        print("4. Escribir ruta manualmente")
        print("5. Salir")
        print("==========================================")

        opcion = input("Seleccione una opción [1-5]: ").strip()

        if opcion == "1":
            nueva_carpeta = abrir_explorador_carpetas(carpeta_actual)
            if nueva_carpeta and nueva_carpeta.is_dir():
                carpeta_actual = nueva_carpeta
                print(f"📁 Carpeta seleccionada: {carpeta_actual}")
                procesar_carpeta(carpeta_actual)
            else:
                print("Operación cancelada o carpeta no válida.")

        elif opcion == "2":
            organize_tree(carpeta_actual)

        elif opcion == "3":
            analyze_tree(carpeta_actual)

        elif opcion == "4":
            ruta_input = input("\nIngrese la ruta de la carpeta: ").strip().strip('"')
            p = Path(ruta_input)
            if p.is_dir():
                carpeta_actual = p
                procesar_carpeta(carpeta_actual)
            else:
                print(f"❌ La ruta no existe o no es una carpeta: {ruta_input}")

        elif opcion in ("5", "q", "exit", "salir"):
            print("\n¡Hasta luego!")
            break

        else:
            print("Opción no válida.")


if __name__ == "__main__":
    main()