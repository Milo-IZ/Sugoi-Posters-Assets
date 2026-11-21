import os
import re
import sys
import unicodedata
from datetime import date, datetime
from urllib.parse import quote

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

# Carpeta base del repositorio de assets (funciona desde Sugoi-Posters-Assets o SugoiPosters-Web-App/tools)
DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))
_candidatos_assets = [
    DIR_SCRIPT,
    os.path.normpath(os.path.join(DIR_SCRIPT, "..", "..", "Sugoi-Posters-Assets")),
]
carpeta_base = next(
    (p for p in _candidatos_assets if os.path.isdir(os.path.join(p, "C-a"))),
    DIR_SCRIPT,
)

# Ruta al products.dart existente (para conservar fechas ya registradas).
RUTAS_BUSQUEDA_DART = [
    os.path.normpath(os.path.join(carpeta_base, "..", "SugoiPosters-Web-App", "lib", "data", "products.dart")),
    os.path.normpath(os.path.join(DIR_SCRIPT, "..", "lib", "data", "products.dart")),
    os.path.join(carpeta_base, "products.dart"),
]
PRODUCTOS_DART_EXISTENTE = next((p for p in RUTAS_BUSQUEDA_DART if os.path.exists(p)), RUTAS_BUSQUEDA_DART[0])

# ── Cargar fechas ya registradas ─────────────────────────────────────────────
def _clave_normalizada(nombre: str) -> str:
    """Clave ASCII canónica para conservar dateAdded incluso tras normalizar nombres."""
    s = re.sub(r"(?<![A-Za-z])([Nn])[°º]\s*(\d+)", r"\1o \2", nombre)
    s = s.replace("°", "o").replace("º", "o")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().lower()


def _leer_fechas_existentes(path: str) -> tuple[dict[str, str], dict[str, str]]:
    """Devuelve ({nombre_exacto: dateAdded}, {clave_ascii: dateAdded}) del products.dart actual."""
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        exact: dict[str, str] = {}
        norm: dict[str, str] = {}
        # Busca pares nombre / dateAdded dentro del mismo bloque Product(...)
        for bloque in re.finditer(r'Product\s*\(.*?\n  \)', content, re.DOTALL):
            b = bloque.group(0)
            n = re.search(r'nombre:\s*"([^"]+)"', b)
            d = re.search(r'dateAdded:\s*"([^"]+)"', b)
            if n and d:
                exact[n.group(1)] = d.group(1)
                norm.setdefault(_clave_normalizada(n.group(1)), d.group(1))
        return exact, norm
    except FileNotFoundError:
        return {}, {}

_fechas_existentes, _fechas_normalizadas = _leer_fechas_existentes(PRODUCTOS_DART_EXISTENTE)
_nuevos_detectados: list[str] = []

def _fecha_para(nombre_producto: str, rutas_locales: list[str]) -> str:
    """
    Retorna la fecha ISO para dateAdded:
      - Si el producto YA existe en products.dart (exacto o normalizado) → conserva su fecha.
      - Si es NUEVO → usa el mtime más reciente de sus imágenes locales.
      - Fallback: fecha de hoy.
    """
    if nombre_producto in _fechas_existentes:
        return _fechas_existentes[nombre_producto]

    clave_norm = _clave_normalizada(nombre_producto)
    if clave_norm in _fechas_normalizadas:
        return _fechas_normalizadas[clave_norm]

    _nuevos_detectados.append(nombre_producto)

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

# URL base del CDN propio en Cloudflare R2 (bucket: sugoi-posters-assets)
base_url = "https://img.sugoipostershn.com/"
_rutas_no_ascii: list[str] = []


def construir_url_imagen(ruta_local: str) -> str:
    """Construye una URL ASCII segura (percent-encoded) para R2 y WhatsApp."""
    relative_path = os.path.relpath(ruta_local, carpeta_base).replace("\\", "/")
    if not relative_path.isascii():
        _rutas_no_ascii.append(relative_path)
    return base_url + quote(relative_path, safe="/-_.!~*'()")


productos = []

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
                    construir_url_imagen(os.path.join(subcategoria_path, f))
                    for f in archivos_pers
                ]
                if not imagenes:
                    continue

                adj = "Personalizada" if categoria_dir == "C-a" else "Personalizado"
                nombre_producto = f"{nombre_categoria} {adj} #1"
                imagenes_dart = "[\n" + ",\n".join([f'      "{img}"' for img in imagenes]) + "\n    ]"
                rutas_locales = [os.path.join(subcategoria_path, f) for f in archivos_pers]
                fecha = _fecha_para(nombre_producto, rutas_locales)
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
                            construir_url_imagen(ruta)
                            for ruta in archivos_variante
                        ]
                        # Mostrar el número tal cual si existe; si no existe, usar 1
                        numero_display = numero_carpeta if numero_carpeta > 0 else 1

                        nombre_producto = f"{nombre_categoria} {nombre_base} #{numero_display}"
                        imagenes_dart = "[\n" + ",\n".join([f'      "{img}"' for img in imagenes_variante]) + "\n    ]"
                        rutas_locales = archivos_variante
                        fecha = _fecha_para(nombre_producto, rutas_locales)
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
                    url = construir_url_imagen(ruta_local)
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
                    url = construir_url_imagen(ruta_elemento)
                    personaje = limpiar_nombre(elemento)
                    personaje = normalize_hashes(personaje)

                    nombre_producto = f"{nombre_categoria} {personaje}"
                    imagenes_dart = "[\n" + f'      "{url}"' + "\n    ]"
                    fecha = _fecha_para(nombre_producto, [ruta_elemento])
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
                        imagenes_internas = [construir_url_imagen(ruta) for ruta in archivos_internos]
                        imagenes_dart = "[\n" + ",\n".join([f'      "{img}"' for img in imagenes_internas]) + "\n    ]"
                        rutas_locales_int = archivos_internos
                        fecha = _fecha_para(nombre_producto, rutas_locales_int)
                        
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
output_local = os.path.join(carpeta_base, "products.dart")
with open(output_local, "w", encoding="utf-8") as f:
    f.write("import '../models/product.dart';\n\n")
    f.write("const List<Product> productos = [\n")
    f.write("\n".join(productos))
    f.write("\n];\n")

# Sincronizar automáticamente con SugoiPosters-Web-App si la carpeta existe
output_webapp = os.path.normpath(os.path.join(carpeta_base, "..", "SugoiPosters-Web-App", "lib", "data", "products.dart"))
webapp_sync_ok = False
if os.path.exists(os.path.dirname(output_webapp)):
    try:
        import shutil
        shutil.copyfile(output_local, output_webapp)
        webapp_sync_ok = True
    except Exception as e:
        print(f"⚠️ No se pudo copiar a Web-App: {e}")

n_nuevos = len(_nuevos_detectados)
print(f"✅ Archivo 'products.dart' generado con {len(productos)} productos ({base_url}).")
if webapp_sync_ok:
    print(f"🔄 Sincronizado automáticamente en: {os.path.normpath(output_webapp)}")
if n_nuevos:
    print(f"   🆕 {n_nuevos} producto(s) nuevo(s) → dateAdded asignado por mtime de archivos.")
else:
    print(f"   ✔  Sin productos nuevos detectados.")
if _rutas_no_ascii:
    print(
        f"   ⚠️  {len(_rutas_no_ascii)} ruta(s) contienen caracteres no-ASCII. "
        "Ejecuta 'python Quitar_espacios.py' antes de hacer push para mantener URLs limpias."
    )
print("   ☁️  Siguiente paso: haz 'git push' en Sugoi-Posters-Assets para sincronizar Cloudflare R2 automáticamente.")