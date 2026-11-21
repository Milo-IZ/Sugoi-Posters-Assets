# Sugoi Posters — Assets & Cloudflare R2 CDN

Repositorio fuente de imágenes del catálogo de **Sugoi Posters HN** (`https://sugoipostershn.com`).  
Las imágenes se sincronizan automáticamente a **Cloudflare R2** (bucket `sugoi-posters-assets`) y se sirven desde **`https://img.sugoipostershn.com/`** junto con miniaturas WebP generadas automáticamente en `_thumbs/360/` y `_thumbs/640/`.

## Flujo diario para agregar o actualizar productos

1. **Colocar imágenes nuevas** en su carpeta de categoría (`C-a`, `S-u`, `P-o`, `S-e`, `Pol`).
2. **Convertir y organizar** *(si vienen en PNG/JPG o sueltas)*:
   ```powershell
   python convertir.py            # PNG/JPG -> WebP
   python organizar_carpetas.py   # Agrupa imágenes sueltas en carpetas
   python Renombrar.py            # Renumera variantes _1.._n (opcional)
   ```
3. **Publicar catálogo (todo en un comando):**
   ```powershell
   # Normaliza ASCII -> genera products.dart -> push a GitHub -> espera sync de R2 -> compila y despliega la Web App
   .\publicar_catalogo.ps1 -Deploy -Message "feat(catalogo): descripcion del lote"
   ```

   También puedes ejecutarlo por partes:
   - `.\publicar_catalogo.ps1` → solo normaliza nombres ASCII y regenera `products.dart` (sin subir nada).
   - `.\publicar_catalogo.ps1 -Push -Message "..."` → además hace push y espera a que Cloudflare R2 termine en verde.
   - `.\publicar_catalogo.ps1 -Deploy -PushWebApp -Message "..."` → hace todo lo anterior y además commitea `lib/data/products.dart` en `SugoiPosters-Web-App`.

## Sincronización manual con R2 (GitHub Actions)

Cada `git push` a `main` que toque `C-a/`, `S-u/`, `P-o/`, `S-e/` o `Pol/` sincroniza **solo los cambios** en segundos.  
Si alguna vez necesitas una auditoría completa o limpiar objetos huérfanos en R2:
- Abre **Actions → Sync Assets to Cloudflare R2 → Run workflow** y elige:
  - `full`: sube cualquier archivo o miniatura faltante.
  - `full_prune`: igual que `full` y borra de R2 lo que ya no existe en Git.
  - `force_thumbs`: regenera todas las miniaturas `360px` y `640px`.
