import os
import re
import sys
from datetime import date, datetime

# Evita UnicodeEncodeError con los emojis al imprimir en consolas Windows (cp1252)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

EXTENSIONES_IMG = (".png", ".jpg", ".jpeg", ".webp")

def buscar_imagenes_rec(carpeta):
    """
    Devuelve las imágenes dentro de 'carpeta' a CUALQUIER profundidad,
    ordenadas por su ruta relativa. Soporta estructuras donde la imagen
    está anidada en una subcarpeta extra (ej. Casca_1/Casca/Casca.webp).
    """
    encontradas = []
    for raiz, _dirs, archivos in os.walk(carpeta):
        for f in archivos:
            if f.lower().endswith(EXTENSIONES_IMG):
                encontradas.append(os.path.join(raiz, f))
    return sorted(encontradas, key=lambda p: os.path.relpath(p, carpeta).lower())

# Configuración del repo
usuario = "Milo-IZ"
repositorio = "sugoi-posters-assets"
rama = "main"
carpeta_base = "."

# Ruta al products.dart existente (para conservar fechas ya registradas).
# Puede ser relativa al lugar desde donde se ejecuta el script.
PRODUCTOS_DART_EXISTENTE = r"D:\Proyectos\sugoi_posters_deploys\lib\data\products.dart"

# ── Cargar fechas ya registradas ─────────────────────────────────────────────
def _leer_fechas_existentes(path: str) -> dict[str, str]:
    """Devuelve {nombre_producto: dateAdded} del products.dart actual."""
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        result = {}
        # Busca pares nombre / dateAdded dentro del mismo bloque Product(...)
        for bloque in re.finditer(r'Product\s*\(.*?\n  \)', content, re.DOTALL):
            b = bloque.group(0)
            n = re.search(r'nombre:\s*"([^"]+)"', b)
            d = re.search(r'dateAdded:\s*"([^"]+)"', b)
            if n and d:
                result[n.group(1)] = d.group(1)
        return result
    except FileNotFoundError:
        return {}

_fechas_existentes: dict[str, str] = _leer_fechas_existentes(PRODUCTOS_DART_EXISTENTE)

def _fecha_para(nombre_producto: str, rutas_locales: list[str]) -> str:
    """
    Retorna la fecha ISO para dateAdded:
      - Si el producto YA existe en products.dart → conserva su fecha.
      - Si es NUEVO → usa el mtime más reciente de sus imágenes locales.
      - Fallback: fecha de hoy.
    """
    if nombre_producto in _fechas_existentes:
        return _fechas_existentes[nombre_producto]

    # Producto nuevo: tomar la fecha de modificación más reciente de los archivos
    tiempos = []
    for ruta in rutas_locales:
        try:
            tiempos.append(os.path.getmtime(ruta))
        except OSError:
            pass
    if tiempos:
        return datetime.fromtimestamp(max(tiempos)).strftime("%Y-%m-%d")

    return date.today().isoformat()
# ─────────────────────────────────────────────────────────────────────────────

# Definición de categorías, precios y descripciones
categorias = {
    "C-a": {"nombre": "Camisa",    "categoria": "Camisas",   "precio": "280", "descripcion": "Camisa de alta calidad inspirada en tu anime favorito. Ideal para el día a día o coleccionar como parte de tu pasión otaku."},
    "S-u": {"nombre": "Suéter",    "categoria": "Sueters",   "precio": "500", "descripcion": "Suéter cómodo y duradero con diseños únicos de tus animes favoritos. Ideal para mantenerte abrigado con estilo otaku."},
    "P-o": {"nombre": "Poster",    "categoria": "Posters",   "precio": "70",  "descripcion": "Poster con impresión premium para dar vida a tus espacios. Perfecto para decorar tu cuarto, oficina o rincón otaku."},
    "S-e": {"nombre": "Separador", "categoria": "Separadores","precio": "25",  "descripcion": "Separador de diseño exclusivo para que nunca pierdas la página en tus mangas y libros. Compacto, resistente y coleccionable."},
    "Pol": {"nombre": "Polaroid",  "categoria": "Polaroids", "precio": "20",  "descripcion": "Polaroid coleccionable con acabado especial. Llévate un recuerdo único de tu anime favorito en formato de bolsillo."},
}

# URL base
base_url = f"https://cdn.jsdelivr.net/gh/{usuario}/{repositorio}@{rama}/"


productos = []
og_jobs = []  # (nombre_producto, ruta_imagen_local) para generar previews OG

# ── Slug e imágenes Open Graph ───────────────────────────────────────────────
_ACENTOS = {
    "á": "a", "à": "a", "ä": "a", "â": "a",
    "é": "e", "è": "e", "ë": "e", "ê": "e",
    "í": "i", "ì": "i", "ï": "i", "î": "i",
    "ó": "o", "ò": "o", "ö": "o", "ô": "o",
    "ú": "u", "ù": "u", "ü": "u", "û": "u",
    "ñ": "n",
}

def slugify(nombre: str) -> str:
    """Replica Product.slug de Dart: minúsculas, sin acentos, [a-z0-9] y el
    resto se vuelve '-' (colapsado y sin guiones en los extremos)."""
    out = []
    last_dash = False
    for ch in nombre.lower():
        n = _ACENTOS.get(ch, ch)
        if re.match(r"[a-z0-9]", n):
            out.append(n)
            last_dash = False
        elif not last_dash:
            out.append("-")
            last_dash = True
    return re.sub(r"^-+|-+$", "", "".join(out))

def generar_imagenes_og(jobs, salida="og", size=(1200, 630)):
    """Genera un JPG <slug>.jpg por producto (poster centrado sobre fondo
    blanco, 1200x630) para usar como og:image en los previews de redes."""
    try:
        from PIL import Image
    except ImportError:
        print("⚠️ Pillow no está instalado (pip install Pillow). Se omiten las imágenes OG.")
        return
    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = Image.LANCZOS

    os.makedirs(salida, exist_ok=True)
    w, h = size
    vistos = set()
    generadas = 0
    for nombre, ruta in jobs:
        slug = slugify(nombre)
        if slug in vistos:
            continue
        vistos.add(slug)
        try:
            src = Image.open(ruta).convert("RGBA")
        except Exception as e:
            print(f"⚠️ OG: no se pudo abrir {ruta}: {e}")
            continue
        src.thumbnail((w, h), resample)
        canvas = Image.new("RGB", (w, h), (255, 255, 255))
        x = (w - src.width) // 2
        y = (h - src.height) // 2
        canvas.paste(src, (x, y), src)
        canvas.save(os.path.join(salida, f"{slug}.jpg"), "JPEG", quality=85, optimize=True)
        generadas += 1
    print(f"🖼️  {generadas} imágenes OG generadas en '{salida}/'.")
# ─────────────────────────────────────────────────────────────────────────────

def limpiar_nombre(nombre_archivo):
    nombre = os.path.splitext(nombre_archivo)[0]
    # quitar sufijos tipo (1) o _1 y convertir "Name_1" -> "Name #1"
    nombre = re.sub(r"[_\s]*\(?(\d+)\)?$", r" #\1", nombre)
    nombre = re.sub(r"[_]+", " ", nombre)
    nombre = re.sub(r"\s{2,}", " ", nombre).strip()
    return nombre

def normalize_hashes(name):
    """
    Normaliza usos de '#' en un nombre para evitar duplicados como 'Name # #3':
    - transforma '# #' -> '#'
    - elimina '#' que NO estén seguidos por un dígito (considerando espacios)
    - limpia espacios repetidos
    """
    s = name
    # Colapsar secuencias de '# #' a '#'
    s = re.sub(r"#\s+#", "#", s)
    # Eliminar '#' que no van seguidos de un dígito (permite espacio entre # y dígito)
    s = re.sub(r"#(?!\s*\d)", "", s)
    # Limpiar espacios sobrantes
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s

def formatear_subcategoria(nombre_carpeta):
    """
    Formatea subcategorías conservando acrónimos (todos en mayúscula) y Title Case para el resto.
    Ej: "DC_Comics" -> "DC Comics", "one_piece" -> "One Piece"
    """
    partes = re.split(r'[_\-]+', nombre_carpeta)
    partes_formateadas = []
    for p in partes:
        p_stripped = p.strip()
        if not p_stripped:
            continue
        # si la parte está ya en mayúsculas (ej. "DC"), la dejamos así
        if p_stripped.isupper():
            partes_formateadas.append(p_stripped)
        else:
            partes_formateadas.append(p_stripped.title())
    return " ".join(partes_formateadas)

def extraer_variante(nombre_carpeta):
    """
    Extrae el nombre base y el número de variante.
    Soporta formatos como:
      - 'Ichigo_Hollow'        -> ('Ichigo Hollow', 0)
      - 'Ichigo_Hollow_1'      -> ('Ichigo Hollow', 1)
      - 'Guts #1'              -> ('Guts', 1)
      - 'Guts-2'               -> ('Guts', 2)
    """
    # permitir separadores _, espacio, -, # antes del número
    match = re.match(r"^(.+?)[_\s#\-]*(\d+)$", nombre_carpeta)
    if match:
        nombre_personaje = match.group(1).replace("_", " ").strip()
        numero_variante = int(match.group(2))
        return nombre_personaje, numero_variante
    # Si no tiene número, es variante 0
    return nombre_carpeta.replace("_", " ").strip(), 0


# --- RECORRIDO DE CARPETAS ---
for categoria_dir in sorted(os.listdir(carpeta_base)):
    if categoria_dir not in categorias:
        continue

    categoria_path = os.path.join(carpeta_base, categoria_dir)
    if not os.path.isdir(categoria_path):
        continue

    tipo = categorias[categoria_dir]
    nombre_categoria = tipo["nombre"]
    categoria_plural = tipo["categoria"]
    precio = tipo["precio"]
    descripcion = tipo["descripcion"]

    # Aplicar la lógica de 'personalizados' a C-a, S-u, P-o y Pol
    if categoria_dir in ("C-a", "S-u", "P-o", "Pol"):
        subcarpetas = sorted(os.listdir(categoria_path))
        personales = [s for s in subcarpetas if s.lower().startswith("1_") or "personaliz" in s.lower()]
        normales = [s for s in subcarpetas if s not in personales]
        orden_final = personales + normales

        for subcategoria_dir in orden_final:
            subcategoria_path = os.path.join(categoria_path, subcategoria_dir)
            if not os.path.isdir(subcategoria_path):
                continue

            es_personalizada_directa = subcategoria_dir.lower().startswith("1_") or "personaliz" in subcategoria_dir.lower()

            if es_personalizada_directa:
                archivos_pers = sorted(
                    f for f in os.listdir(subcategoria_path)
                    if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
                )
                imagenes = [
                    base_url + os.path.relpath(os.path.join(subcategoria_path, f), carpeta_base).replace("\\", "/")
                    for f in archivos_pers
                ]
                if not imagenes:
                    continue

                adj = "Personalizada" if categoria_dir == "C-a" else "Personalizado"
                nombre_producto = f"{nombre_categoria} {adj} #1"
                imagenes_dart = "[\n" + ",\n".join([f'      "{img}"' for img in imagenes]) + "\n    ]"
                rutas_locales = [os.path.join(subcategoria_path, f) for f in archivos_pers]
                fecha = _fecha_para(nombre_producto, rutas_locales)
                og_jobs.append((nombre_producto, rutas_locales[0]))
                productos.append(f'''  Product(
    nombre: "{nombre_producto}",
    precio: "{precio}",
    descripcion: "{descripcion}",
    categoria: "{categoria_plural}",
    imagenes: {imagenes_dart},
    subcategoria: "",
    dateAdded: "{fecha}",
  ),''')
                continue

            subcategoria_limpia = formatear_subcategoria(subcategoria_dir)

            internas = [v for v in sorted(os.listdir(subcategoria_path)) if os.path.isdir(os.path.join(subcategoria_path, v))]
            archivos_directos = [f for f in sorted(os.listdir(subcategoria_path))
                                 if os.path.isfile(os.path.join(subcategoria_path, f)) and f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]

            # 1) Carpetas internas (ej. One_Piece/Brook Wanted)
            if internas:
                for variante_dir in internas:
                    variante_path = os.path.join(subcategoria_path, variante_dir)
                    if not os.path.isdir(variante_path):
                        continue

                    archivos_variante = buscar_imagenes_rec(variante_path)
                    if archivos_variante:
                        nombre_base, numero_carpeta = extraer_variante(variante_dir)
                        nombre_base = normalize_hashes(nombre_base)

                        imagenes_variante = [
                            base_url + os.path.relpath(ruta, carpeta_base).replace("\\", "/")
                            for ruta in archivos_variante
                        ]
                        # Mostrar el número tal cual si existe; si no existe, usar 1
                        numero_display = numero_carpeta if numero_carpeta > 0 else 1

                        nombre_producto = f"{nombre_categoria} {nombre_base} #{numero_display}"
                        imagenes_dart = "[\n" + ",\n".join([f'      "{img}"' for img in imagenes_variante]) + "\n    ]"
                        rutas_locales = archivos_variante
                        fecha = _fecha_para(nombre_producto, rutas_locales)
                        og_jobs.append((nombre_producto, archivos_variante[0]))
                        productos.append(f'''  Product(
    nombre: "{nombre_producto}",
    precio: "{precio}",
    descripcion: "{descripcion}",
    categoria: "{categoria_plural}",
    imagenes: {imagenes_dart},
    subcategoria: "{subcategoria_limpia}",
    dateAdded: "{fecha}",
  ),''')

            # 2) Archivos directos en la subcategoria (Se unificó la lógica para TODAS las categorías)
            if archivos_directos:
                for file in archivos_directos:
                    ruta_local = os.path.join(subcategoria_path, file)
                    relative_path = os.path.relpath(ruta_local, carpeta_base).replace("\\", "/")
                    url = base_url + relative_path
                    personaje = limpiar_nombre(file)
                    personaje = normalize_hashes(personaje)
                    
                    # Logica específica si era de polaroid anime
                    if categoria_dir == "Pol" and subcategoria_dir.lower() == "anime":
                        subcategoria_final = personaje 
                    else:
                        subcategoria_final = subcategoria_limpia

                    nombre_producto = f"{nombre_categoria} {personaje}"
                    imagenes_dart = "[\n" + f'      "{url}"' + "\n    ]"
                    fecha = _fecha_para(nombre_producto, [ruta_local])
                    og_jobs.append((nombre_producto, ruta_local))
                    productos.append(f'''  Product(
    nombre: "{nombre_producto}",
    precio: "{precio}",
    descripcion: "{descripcion}",
    categoria: "{categoria_plural}",
    imagenes: {imagenes_dart},
    subcategoria: "{subcategoria_final}",
    dateAdded: "{fecha}",
  ),''')

    # Resto de categorías (S-e, etc.)
    else:
        for subcategoria_dir in sorted(os.listdir(categoria_path)):
            subcategoria_path = os.path.join(categoria_path, subcategoria_dir)
            if not os.path.isdir(subcategoria_path):
                continue

            subcategoria_limpia = formatear_subcategoria(subcategoria_dir)

            # Iterar los elementos dentro para admitir tanto archivos como carpetas
            for elemento in sorted(os.listdir(subcategoria_path)):
                ruta_elemento = os.path.join(subcategoria_path, elemento)
                
                # Caso A: Archivo de imagen directo
                if os.path.isfile(ruta_elemento) and elemento.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    relative_path = os.path.relpath(ruta_elemento, carpeta_base).replace("\\", "/")
                    url = base_url + relative_path
                    personaje = limpiar_nombre(elemento)
                    personaje = normalize_hashes(personaje)

                    nombre_producto = f"{nombre_categoria} {personaje}"
                    imagenes_dart = "[\n" + f'      "{url}"' + "\n    ]"
                    fecha = _fecha_para(nombre_producto, [ruta_elemento])
                    og_jobs.append((nombre_producto, ruta_elemento))
                    productos.append(f'''  Product(
    nombre: "{nombre_producto}",
    precio: "{precio}",
    descripcion: "{descripcion}",
    categoria: "{categoria_plural}",
    imagenes: {imagenes_dart},
    subcategoria: "{subcategoria_limpia}",
    dateAdded: "{fecha}",
  ),''')
                    
                # Caso B: Carpeta interna (ej. Separadores con múltiples imágenes para el mismo personaje)
                elif os.path.isdir(ruta_elemento):
                    archivos_internos = buscar_imagenes_rec(ruta_elemento)
                    if archivos_internos:
                        nombre_base, numero_carpeta = extraer_variante(elemento)
                        nombre_base = normalize_hashes(nombre_base)
                        numero_display = numero_carpeta if numero_carpeta > 0 else 1

                        nombre_producto = f"{nombre_categoria} {nombre_base} #{numero_display}"
                        imagenes_internas = [base_url + os.path.relpath(ruta, carpeta_base).replace("\\", "/") for ruta in archivos_internos]
                        imagenes_dart = "[\n" + ",\n".join([f'      "{img}"' for img in imagenes_internas]) + "\n    ]"
                        rutas_locales_int = archivos_internos
                        fecha = _fecha_para(nombre_producto, rutas_locales_int)
                        og_jobs.append((nombre_producto, archivos_internos[0]))
                        
                        productos.append(f'''  Product(
    nombre: "{nombre_producto}",
    precio: "{precio}",
    descripcion: "{descripcion}",
    categoria: "{categoria_plural}",
    imagenes: {imagenes_dart},
    subcategoria: "{subcategoria_limpia}",
    dateAdded: "{fecha}",
  ),''')

# --- GENERAR ARCHIVO DART ---
with open("products.dart", "w", encoding="utf-8") as f:
    f.write("import '../models/product.dart';\n\n")
    f.write("const List<Product> productos = [\n")
    f.write("\n".join(productos))
    f.write("\n];\n")

nuevos = [p for p in productos if p.split('dateAdded: "')[1].split('"')[0] not in _fechas_existentes.values()
          or any(n not in _fechas_existentes for n in [p.split('nombre: "')[1].split('"')[0]])]
n_nuevos = sum(1 for p in productos
               if p.split('nombre: "')[1].split('"')[0] not in _fechas_existentes)
print(f"✅ Archivo 'products.dart' generado con {len(productos)} productos.")

# --- GENERAR IMÁGENES OG (preview de redes sociales) ---
generar_imagenes_og(og_jobs)

if n_nuevos:
    print(f"   🆕 {n_nuevos} producto(s) nuevo(s) → dateAdded asignado por mtime de archivos.")
else:
    print(f"   ✔  Sin productos nuevos detectados.")