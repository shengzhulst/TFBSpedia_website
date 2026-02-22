# Cell Line/Tissue Filter Feature – Code Changes

## Summary

Added a new feature to filter search results by cell line/tissue. Users can choose from a dropdown on the main page (and search results page) to constrain searches to a specific cell line/tissue. The default shows all results (no constraint).

### Follow-up optimisations (v2)
- **Dropdown population** now reads from pre-built CSV files (`cell_tissue_unique_{species}.csv`) instead of querying the database.
- **Search filtering** now uses a pre-built CSV mapping (`cell_line_ID_table_{species}.csv`) that maps cell tissue names → TFBS IDs. A module-level in-memory cache (`_cell_line_ids_cache`) ensures each CSV is loaded only once per process. SQL queries use `WHERE "ID" = ANY(%s)` instead of JOIN/EXISTS against `TFBS_cell_or_tissue`, giving a major performance improvement.

---

## Files Modified

### 1. `home/views.py`

#### 1a. New function: `get_all_cell_tissues()`
Added after `get_all_tf_names()`.

```python
def get_all_cell_tissues(request):
    """
    Fetch all unique cell/tissue types from TFBS_cell_or_tissue table for autocomplete/dropdown.
    """
    species = request.GET.get('species', 'human')
    db_alias = 'human' if species == 'human' else 'mouse'

    try:
        with connections[db_alias].cursor() as cursor:
            cursor.execute('''
                SELECT DISTINCT "cell_tissue"
                FROM "TFBS_cell_or_tissue"
                WHERE "cell_tissue" IS NOT NULL
                ORDER BY "cell_tissue"
            ''')
            cell_tissues = [row[0] for row in cursor.fetchall()]

        return JsonResponse({
            'success': True,
            'cell_tissues': cell_tissues
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
```

#### 1b. Modified `search_results()` view
Added `cell_line` parameter (from GET request) and passed it to template context.

**Changed:**
- Added `cell_line = request.GET.get('cell_line', '')`
- Added `'cell_line': cell_line` to context dict

#### 1c. Modified `TFBSViewSet.list()`
Added `cell_line` from query params and passed it to search functions.

**Changed:**
- Added `cell_line = request.query_params.get('cell_line', '') or None`
- Passed `cell_line=cell_line` to `search_by_location()` and `search_by_tf_name()`

#### 1d. Modified `download_results()`
Added `cell_line` from GET params and passed to search functions.

**Changed:**
- Added `cell_line = request.GET.get('cell_line', '') or None`
- Passed `cell_line=cell_line` to `search_by_location()` and `search_by_tf_name()`

#### 1e. Modified `search_by_location()`
Added optional `cell_line` parameter. When provided, JOINs with `TFBS_cell_or_tissue` and filters by `cell_tissue`.

**Signature changed:**
```python
def search_by_location(db_alias, chromosome, start, end, request, no_pagination=False, cell_line=None):
```

When `cell_line` is set, the SQL queries include:
```sql
JOIN "TFBS_cell_or_tissue" ct ON ct."ID" = p."ID"
... AND ct."cell_tissue" = %s
```

This applies to all four cases: chromosome-only / genomic region × paginated / no_pagination.

#### 1f. Modified `search_by_tf_name()`
Added optional `cell_line` parameter. When provided, uses `EXISTS` subquery to filter by cell_tissue.

**Signature changed:**
```python
def search_by_tf_name(db_alias, tf_name, request, no_pagination=False, cell_line=None):
```

When `cell_line` is set:
- Count uses a direct `COUNT(DISTINCT p."ID")` query (bypasses pre-calculated `tfbs_name_counts` since those don't account for cell line filter)
- Data queries add:
```sql
AND EXISTS (
    SELECT 1 FROM "TFBS_cell_or_tissue" ct
    WHERE ct."ID" = p."ID"
    AND ct."cell_tissue" = %s
)
```

---

### 2. `home/urls.py`

Added URL for new `get_all_cell_tissues` API endpoint:

```python
path('api/cell-tissues/', views.get_all_cell_tissues, name='get_all_cell_tissues'),
```

---

### 3. `templates/pages/index.html`

#### 3a. Added cell line dropdown inside text search form
Added after the species radio buttons, before the Search button:

```html
<div class="cell-line-filter" style="margin: 10px 0;">
    <label for="cell-line-select" style="font-size:16px; margin-right:8px;">Cell Line/Tissue:</label>
    <select id="cell-line-select" name="cell_line" style="padding:6px 12px; font-size:15px; border:2px solid #ccc; border-radius:4px; min-width:200px;">
        <option value="">All cell lines/tissues</option>
    </select>
</div>
```

#### 3b. Added JavaScript functions `loadCellTissues()`
- Called on DOMContentLoaded to populate dropdown from `/api/cell-tissues/?species=...`
- Re-called when species radio selection changes
- Preserves previously selected value when reloading

---

### 4. `templates/pages/search_results.html`

#### 4a. Added cell line dropdown in the search form
Added a `<select id="cell-line-select" name="cell_line">` between the species radio buttons and the Search button. Uses Bootstrap `form-select` class.

#### 4b. Updated search info heading
Changed:
```html
<h2>Search Results for "{{ query }}" in {{ species|title }} database</h2>
```
To:
```html
<h2>Search Results for "{{ query }}" in {{ species|title }} database{% if cell_line %} — Cell line: {{ cell_line }}{% endif %}</h2>
```

#### 4c. Updated DataTables AJAX call
Added `d.cell_line = '{{ cell_line|escapejs }}';` to the data function so the API receives the selected cell line filter.

#### 4d. Updated Download button handler
Added `cell_line` parameter to the download URL when a cell line is selected.

#### 4e. Added `loadCellTissues()` JavaScript function
Same as in index.html, restores the currently selected cell line value from the template context.

---

## Follow-up Changes (v2) — Performance Optimisations

### 1. `home/views.py` — `get_all_cell_tissues()` rewritten

Old: queried `TFBS_cell_or_tissue` table in the database on every request.

New: reads the pre-built CSV file `staticfiles/documents/cell_tissue_unique_{species}.csv` (no database hit):

```python
def get_all_cell_tissues(request):
    species = request.GET.get('species', 'human')
    csv_path = f"staticfiles/documents/cell_tissue_unique_{species}.csv"
    cell_tissues = []
    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get('cell_tissue', '').strip()
                if name:
                    cell_tissues.append(name)
    return JsonResponse({'success': True, 'cell_tissues': cell_tissues})
```

### 2. `home/views.py` — New module-level cache + `load_cell_line_ids()`

Added at the top of the file (after imports):

```python
_cell_line_ids_cache = {}

def load_cell_line_ids(species):
    """
    Load cell_tissue -> list of IDs mapping from the pre-built CSV file.
    Result is cached in memory so the CSV is only read once per species per process.
    """
    if species in _cell_line_ids_cache:
        return _cell_line_ids_cache[species]

    csv_path = f"staticfiles/documents/cell_line_ID_table_{species}.csv"
    mapping = {}
    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ct = row.get('cell_tissue', '').strip()
                try:
                    tfbs_id = int(row.get('ID', '').strip())
                except ValueError:
                    continue
                if ct:
                    mapping.setdefault(ct, []).append(tfbs_id)

    _cell_line_ids_cache[species] = mapping
    return mapping
```

CSV format used: `staticfiles/documents/cell_line_ID_table_{species}.csv` — columns: `ID,cell_tissue`

### 3. `home/views.py` — `search_by_location()` updated

Old: used JOIN with `TFBS_cell_or_tissue` table.

New: resolves the ID list from the cache before entering the database, then filters with `WHERE "ID" = ANY(%s)`:

```python
# At the top of search_by_location()
allowed_ids = None
if cell_line:
    species = 'human' if db_alias == 'human' else 'mouse'
    mapping = load_cell_line_ids(species)
    allowed_ids = mapping.get(cell_line, [])
    if not allowed_ids:
        return [], 0  # Short-circuit: no IDs for this cell line
```

All SQL queries now use: `AND "ID" = ANY(%s)` instead of a JOIN.

### 4. `home/views.py` — `search_by_tf_name()` updated

Old: used `AND EXISTS (SELECT 1 FROM "TFBS_cell_or_tissue" ...)` subquery, and counted using a separate database query.

New: resolves ID list from cache first, then uses `AND p."ID" = ANY(%s)`:

```python
# At the top of search_by_tf_name()
allowed_ids = None
if cell_line:
    species = 'human' if db_alias == 'human' else 'mouse'
    mapping = load_cell_line_ids(species)
    allowed_ids = mapping.get(cell_line, [])
    if not allowed_ids:
        return [], 0
```

Count query (when cell_line active):
```sql
SELECT COUNT(DISTINCT p."ID")
FROM "TFBS_position" p
WHERE p."ID" = ANY(%s)
AND EXISTS (
    SELECT 1 FROM "TFBS_name" n
    WHERE n."ID" = p."ID"
    AND (n."TFBS" = %s OR n."predicted_TFBS" = %s)
)
```

---

## Follow-up Changes (v3) — New File Structure, Batch Filter, Bug Fixes

### 1. `home/views.py` — `load_cell_line_ids()` rewritten

Old: read from a single combined CSV (`cell_line_ID_table_{species}.csv`).

New: reads from individual per-cell-line files:
`staticfiles/documents/cell_lines_ID_{species}/{cell_tissue}.csv`

Each file has a single `ID` column. The cache key is now `(species, cell_tissue)` so only the requested cell line's file is loaded (lazy per-file loading):

```python
_cell_line_ids_cache = {}  # (species, cell_tissue) -> [id, ...]

def load_cell_line_ids(species, cell_tissue=None):
    cache_key = (species, cell_tissue)
    if cache_key in _cell_line_ids_cache:
        return _cell_line_ids_cache[cache_key]
    ids = []
    if cell_tissue:
        csv_path = os.path.join('staticfiles', 'documents',
                                f'cell_lines_ID_{species}', f'{cell_tissue}.csv')
        if os.path.exists(csv_path):
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        ids.append(int(row.get('ID', '').strip()))
                    except ValueError:
                        continue
    _cell_line_ids_cache[cache_key] = ids
    return ids
```

All callers updated: `load_cell_line_ids(species, cell_line)` (passing the cell_line directly).

### 2. `home/views.py` — Batch search functions support `cell_line`

**`batch_search_by_tf_name()`**: Added `cell_line=None` parameter. Resolves ID list via `load_cell_line_ids()` and adds `WHERE p."ID" = ANY(%s)` to count and data queries. Falls back to `tfbs_name_counts` when no filter is active.

**`batch_search_by_location()`**: Added `cell_line=None` parameter. All chromosome-only and region SQL queries add `AND "ID" = ANY(%s)` when cell_line is active.

**`batch_search()` view**: Reads `cell_line` from POST and adds it as a URL parameter on the redirect to `batch_results`.

**`batch_results()` view**: Reads `cell_line` from GET and passes it to context.

**`BatchTFBSViewSet.list()`**: Reads `cell_line` from query_params and passes to both batch functions.

### 3. `templates/pages/index.html` — Cell line dropdown added to file upload section

- Added `<select id="batch-cell-line-select" name="cell_line">` to the file upload form
- Added `loadBatchCellTissues()` JS function (mirrors `loadCellTissues()`)
- Species radio listeners wired separately for each section

### 4. `templates/pages/batch_results.html` — Cell line plumbed through

- Heading shows `— Cell line: {{ cell_line }}` when active
- DataTables AJAX passes `d.cell_line = '{{ cell_line|escapejs }}'`
- Download URL includes `cell_line` param when active

### 5. `templates/pages/tfbs_details.html` — Two bug fixes

**Bug 1 — Histone extra info not showing:**
Template used `{{ annotation.extra_info }}` but the view dict uses key `extra`.
Fixed: changed template to `{{ annotation.extra }}`.

**Bug 2 — Cookbook_ChIP display name:**
Added conditional in the Type column:
```html
{% if annotation.type == 'Cookbook_ChIP' %}Codebook_ChIP{% else %}{{ annotation.type }}{% endif %}
```

### 6. `templates/pages/evaluation_metrics.html` — Typo fix

Changed "Cookbook annotations" → "Codebook annotations" in the Important Score formula.

---

## Follow-up Changes (v4) — TFBS Type Filter, TF Count CSV, Advanced Search UI

### 1. `templates/pages/tfbs_details.html` — Additional typo fix

Extended the Type column conditional to also handle `Cookbook_GHT_SELEX`:
```html
{% if annotation.type == 'Cookbook_ChIP' %}Codebook_ChIP{% elif annotation.type == 'Cookbook_GHT_SELEX' %}Codebook_GHT_SELEX{% else %}{{ annotation.type }}{% endif %}
```

### 2. `home/views.py` — TF count CSV cache

Added at module level:
- `_tf_count_cache = {}` — maps `species -> {(cell_tissue, tf_name): {'all': n, 'chip': n, 'predicted': n}}`
- `load_tf_count_data(species)` — reads `staticfiles/documents/cell_line_TF_count_{species}.csv` once and caches
- `get_tf_count_from_csv(species, cell_tissue, tf_name, tfbs_type='all')` — returns count from cache
- `_get_name_condition_and_params(tf_name, tfbs_type)` — returns SQL condition fragment + params for TFBS_name filter

CSV format: `cell_tissue,TFBS,predicted_TFBS,count_of_id`

### 3. `home/views.py` — `search_by_tf_name()` updated

**Signature changed:**
```python
def search_by_tf_name(db_alias, tf_name, request, no_pagination=False, cell_line=None, tfbs_type='all'):
```

Changes:
- When `cell_line` active: uses `get_tf_count_from_csv()` instead of a DB COUNT query
- When no `cell_line`: selects the correct column from `tfbs_name_counts` based on `tfbs_type` (`all_count` / `tfbs_count` / `predicted_tfbs_count`)
- All data queries use `_get_name_condition_and_params()` for the name filter condition

### 4. `home/views.py` — `batch_search_by_tf_name()` updated

**Signature changed:**
```python
def batch_search_by_tf_name(db_alias, tf_names, request=None, no_pagination=False, cell_line=None, tfbs_type='all'):
```

Changes:
- When `cell_line` active: sums `get_tf_count_from_csv()` across all TF names instead of DB COUNT
- When no `cell_line`: uses correct `tfbs_name_counts` column based on `tfbs_type`; sums across all returned rows
- Data queries use `tfbs_type`-aware IN clause condition

### 5. `home/views.py` — Views updated for `tfbs_type`

All the following now read and pass `tfbs_type`:
- `search_results()` — reads from GET, passes to context
- `TFBSViewSet.list()` — reads from query_params, passes to `search_by_tf_name()`
- `download_results()` — reads from GET, passes to `search_by_tf_name()`
- `batch_search()` — reads from POST, adds to redirect URL
- `batch_results()` — reads from GET, passes to context
- `BatchTFBSViewSet.list()` — reads from query_params, passes to `batch_search_by_tf_name()`
- `download_batch_results()` — reads from GET, passes to batch functions

### 6. `templates/pages/index.html` — Advanced Search collapsible

Both text search and file upload sections now have:
- A clickable "Advanced Search Options" button (▶/▼ triangle toggle)
- A hidden panel containing:
  - Cell Line/Tissue `<select>` (existing, moved into panel)
  - TFBS Type `<select>` with options: TFBS/Predicted TFBS (all) | TFBS (ChIP-seq) | Predicted TFBS (ATAC-seq, DNase-seq)
- `toggleAdvancedSearch(section)` JS function handles open/close

### 7. `templates/pages/search_results.html` — Advanced Search collapsible + TFBS type

- Replaced inline cell line dropdown with a collapsible Advanced Search panel (same pattern)
- Panel contains both cell line and TFBS type selects
- Panel auto-opens when `cell_line` or `tfbs_type` is active (so user sees active filters)
- AJAX data function adds `d.tfbs_type = '{{ tfbs_type|escapejs }}'`
- Download button includes `tfbs_type` param when not 'all'
- Heading shows active TFBS type filter

### 8. `templates/pages/batch_results.html` — TFBS type plumbed through

- AJAX data function adds `d.tfbs_type = '{{ tfbs_type|escapejs }}'`
- Download button includes `tfbs_type` param when not 'all'
- Heading shows active TFBS type filter
