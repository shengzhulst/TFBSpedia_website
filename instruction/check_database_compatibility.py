"""
Verify that a loaded TFBSpedia database still satisfies everything the website
needs from it.

Run after loading a new dump, before pointing the site at it:

    python instruction/check_database_compatibility.py            # both species
    python instruction/check_database_compatibility.py human      # just one

Three layers of checking, from cheapest to most conclusive:

  1. Schema contract  -- every table and column the app addresses by name exists,
     and the enum types still carry the labels the app filters on.
  2. Index contract   -- the indexes the CSV downloads depend on are present.
     Without them a download of a large TF falls back to scanning a 200M+ row
     table and the reverse proxy times out (the original "502 Proxy Error").
  3. Live queries     -- every query shape in home/views.py is executed against
     the database, so a change the schema check cannot see (a renamed enum
     label, a dropped index, an incompatible type) still surfaces here.

Exits non-zero if anything fails, so it can gate a deployment.
"""

import sys
from collections import OrderedDict

import psycopg2

DB_NAMES = {'human': 'tfbspedia_human', 'mouse': 'tfbspedia_mouse'}
DB_CONFIG = dict(user='postgres', password='', host='localhost', port='5432')

# Every table the site addresses by name, with the columns it reads.  Taken from
# the SQL in home/views.py; if a query there starts using a new column, add it
# here too so the check keeps its value.
REQUIRED = OrderedDict([
    ('TFBS_position',              ['ID', 'seqnames', 'start', 'end']),
    ('TFBS_name',                  ['ID', 'TFBS', 'predicted_TFBS']),
    ('TFBS_cell_or_tissue',        ['ID', 'cell_tissue']),
    ('TFBS_tech',                  ['ID', 'tech']),
    ('TFBS_source',                ['ID', 'source']),
    ('tfbs_name_counts',           ['tfbs', 'all_count', 'tfbs_count', 'predicted_tfbs_count']),
    ('tfbs_confident_score',       ['id', 'confident_score']),
    ('tfbs_importance_score',      ['id', 'importance_score']),
    # Region detail page, "Specific TF table": where each TF binds inside a
    # region.  tf_evidence is partitioned by region_id across one partition per
    # chromosome; querying the parent lets Postgres prune to the right one.
    ('tf_evidence',                ['region_id', 'tf_id', 'cell_id', 'evidence',
                                    'site_start_off', 'site_end_off']),
    ('tf_dictionary',              ['tf_id', 'tf_symbol']),
    ('cell_dictionary',            ['cell_id', 'cell_label']),
    # Region detail page: each annotation is a link table joined to its own table.
    ('TFBS_to_enhancer',           ['ID', 'enhancer_ID']),
    ('Enhancer_GB',                ['enhancer_ID', 'seqnames', 'start', 'end']),
    ('TFBS_to_promoter',           ['ID', 'promoter_ID']),
    ('Promoter',                   ['promoter_ID', 'seqnames', 'start', 'end']),
    ('TFBS_to_histone',            ['ID', 'histone_ID']),
    ('histone',                    ['histone_ID', 'seqnames', 'start', 'end', 'histone']),
    ('TFBS_to_cCREs',              ['ID', 'cCREs_ID']),
    ('cCREs',                      ['cCREs_ID', 'seqnames', 'start', 'end']),
    ('TFBS_to_rE2G',               ['ID', 'rE2G_ID']),
    ('rE2G',                       ['rE2G_ID', 'seqnames', 'start', 'end', 'gene']),
    ('TFBS_to_TE',                 ['ID', 'TE_ID']),
    ('TE',                         ['TE_ID', 'seqnames', 'start', 'end']),
    ('TFBS_to_GWAS',               ['ID', 'GWAS_ID']),
    ('GWAS',                       ['GWAS_ID', 'seqnames', 'start', 'end', 'rs_ID']),
    ('TFBS_to_eQTL',               ['ID', 'eQTL_ID']),
    ('eQTL',                       ['eQTL_ID', 'seqnames', 'start', 'end', 'tissue']),
    ('TFBS_to_blacklist',          ['ID', 'blacklist_ID']),
    ('blacklist',                  ['blacklist_ID', 'seqnames', 'start', 'end']),
    ('TFBS_to_variable_CpG',       ['ID', 'variable_CpG_ID']),
    ('variable_CpG',               ['variable_CpG_ID', 'seqnames', 'start', 'end']),
    ('TFBS_to_Cookbook_ChIP',      ['ID', 'Cookbook_ChIP_ID']),
    ('Cookbook_ChIP',              ['Cookbook_ChIP_ID', 'seqnames', 'start', 'end', 'TF_name']),
    ('TFBS_to_Cookbook_GHT_SELEX', ['ID', 'Cookbook_GHT_SELEX_ID']),
    ('Cookbook_GHT_SELEX',         ['Cookbook_GHT_SELEX_ID', 'seqnames', 'start', 'end', 'TF_name']),
])

# Enum labels the app puts in front of users.  Extra labels are fine and are
# reported; missing ones break a filter or a home-page figure.
REQUIRED_ENUMS = {
    'tf_tech': ['ChIP-seq', 'ATAC-seq', 'DNase-seq'],
    'chromosome': ['chr1', 'chrX', 'chrY'],
}

# tf_evidence.evidence is a single char the detail page turns into a label:
# 'b' = measured by ChIP-seq, 'p' = motif predicted in open chromatin.
# Verified against TFBS_name when the v2 data was loaded.
REQUIRED_EVIDENCE_CODES = {'b', 'p'}

# See instruction/sql_index_for_downloads.sql.
REQUIRED_INDEXES = {
    'TFBS_name': ['tfbs_name_tfbs_id_idx', 'tfbs_name_predicted_id_idx'],
}

# Django keeps its own tables in whichever database is the "default" alias.
# core/settings.py points that at the mouse database, so reloading mouse drops
# them and `manage.py migrate` has to be re-run.
DJANGO_TABLES = ['django_migrations', 'django_session', 'auth_user', 'home_userprofile']


class Report:
    def __init__(self):
        self.failures = []
        self.warnings = []

    def ok(self, message):
        print(f'    ok    {message}')

    def warn(self, message):
        self.warnings.append(message)
        print(f'    WARN  {message}')

    def fail(self, message):
        self.failures.append(message)
        print(f'    FAIL  {message}')


def check_schema(cursor, report):
    print('  schema contract')
    cursor.execute("""
        SELECT c.relname, a.attname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
    """)
    present = {}
    for table, column in cursor.fetchall():
        present.setdefault(table, set()).add(column)

    missing_tables, missing_columns = [], []
    for table, columns in REQUIRED.items():
        if table not in present:
            missing_tables.append(table)
            continue
        gone = [c for c in columns if c not in present[table]]
        if gone:
            missing_columns.append(f'{table}.{{{", ".join(gone)}}}')

    if missing_tables:
        report.fail(f'missing tables: {", ".join(missing_tables)}')
    if missing_columns:
        report.fail(f'missing columns: {", ".join(missing_columns)}')
    if not missing_tables and not missing_columns:
        report.ok(f'all {len(REQUIRED)} required tables and their columns present')

    extra = sorted(t for t in set(present) - set(REQUIRED) - set(DJANGO_TABLES)
                   if not t.startswith('tf_evidence_'))
    if extra:
        print(f'    note  {len(extra)} table(s) present that the site does not use yet: '
              f'{", ".join(extra[:6])}{" ..." if len(extra) > 6 else ""}')


def check_enums(cursor, report):
    print('  enum labels')
    for enum, needed in REQUIRED_ENUMS.items():
        cursor.execute("""
            SELECT e.enumlabel
            FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid
            WHERE t.typname = %s
        """, [enum])
        labels = {row[0] for row in cursor.fetchall()}
        if not labels:
            report.fail(f'enum type "{enum}" does not exist')
            continue
        gone = [v for v in needed if v not in labels]
        if gone:
            report.fail(f'{enum} is missing label(s): {", ".join(gone)}')
        else:
            report.ok(f'{enum}: {len(labels)} labels, all required ones present')


def check_evidence_codes(cursor, report):
    print('  tf_evidence codes')
    cursor.execute('SELECT DISTINCT "evidence" FROM "tf_evidence" '
                   'WHERE "region_id" < 100000')
    found = {row[0] for row in cursor.fetchall()}
    unexpected = found - REQUIRED_EVIDENCE_CODES
    if unexpected:
        report.fail(f'unknown evidence code(s) {sorted(unexpected)} -- the detail page '
                    f'labels only {sorted(REQUIRED_EVIDENCE_CODES)}')
    else:
        report.ok(f'evidence codes {sorted(found)} all map to a label')


def check_indexes(cursor, report):
    print('  download indexes')
    for table, indexes in REQUIRED_INDEXES.items():
        cursor.execute("SELECT indexname FROM pg_indexes WHERE tablename = %s", [table])
        present = {row[0] for row in cursor.fetchall()}
        for index in indexes:
            if index in present:
                report.ok(f'{index}')
            else:
                report.fail(f'{index} missing on "{table}" -- CSV downloads will time out; '
                            f'run instruction/sql_index_for_downloads.sql')


def check_queries(cursor, species, report):
    """Run one of every query shape the site issues."""
    print('  live queries')

    cursor.execute('SELECT count(*) FROM "TFBS_position"')
    regions = cursor.fetchone()[0]

    cursor.execute('SELECT "tfbs" FROM "tfbs_name_counts" '
                   "WHERE \"tfbs\" <> 'UNKNOWN' ORDER BY \"all_count\" DESC LIMIT 1")
    row = cursor.fetchone()
    if not row:
        report.fail('tfbs_name_counts is empty -- autocomplete and search will return nothing')
        return
    tf = row[0]

    cursor.execute('SELECT "seqnames", "start", "end", "ID" FROM "TFBS_position" LIMIT 1')
    seqnames, start, end, region_id = cursor.fetchone()

    checks = [
        ('home page: regions per chromosome',
         'SELECT "seqnames", count(*) FROM "TFBS_position" GROUP BY 1', []),
        ('home page: regions per assay',
         'SELECT "tech", count(*) FROM "TFBS_tech" GROUP BY 1', []),
        ('home page: regions per source',
         'SELECT "source", count(*) FROM "TFBS_source" GROUP BY 1', []),
        ('home page: confidence distribution',
         'SELECT "confident_score", count(*) FROM "tfbs_confident_score" GROUP BY 1', []),
        ('home page: importance distribution',
         'SELECT "importance_score", count(*) FROM "tfbs_importance_score" GROUP BY 1', []),
        ('search by TF name (paginated)',
         '''SELECT DISTINCT p."ID", p."seqnames", p."start", p."end"
            FROM "TFBS_position" p
            WHERE EXISTS (SELECT 1 FROM "TFBS_name" n WHERE n."ID" = p."ID"
                          AND (n."TFBS" = %s OR n."predicted_TFBS" = %s))
            OFFSET 0 LIMIT 25''', [tf, tf]),
        ('search by TF name: count lookup',
         'SELECT all_count, tfbs_count, predicted_tfbs_count FROM tfbs_name_counts WHERE tfbs = %s',
         [tf]),
        ('search by region',
         '''SELECT "ID", "seqnames", "start", "end" FROM "TFBS_position"
            WHERE "seqnames" = %s AND "start" >= %s AND "end" <= %s
            ORDER BY "start" LIMIT 25''', [seqnames, start, end]),
        ('download: TF ids via the index-only union',
         '''SELECT "ID" FROM (
                SELECT "ID" FROM "TFBS_name" WHERE "TFBS" IN (%s)
                UNION
                SELECT "ID" FROM "TFBS_name" WHERE "predicted_TFBS" IN (%s)
            ) src ORDER BY "ID" LIMIT 5000''', [tf, tf]),
        ('download: rows with both scores',
         '''SELECT p."seqnames", p."start", p."end", p."ID",
                   c."confident_score", i."importance_score"
            FROM "TFBS_position" p
            LEFT JOIN "tfbs_confident_score"  c ON c."id" = p."ID"
            LEFT JOIN "tfbs_importance_score" i ON i."id" = p."ID"
            WHERE p."ID" = ANY(%s) ORDER BY p."ID"''', [[region_id]]),
        ('detail page: TF names for a region',
         'SELECT "TFBS", "predicted_TFBS" FROM "TFBS_name" WHERE "ID" = %s', [region_id]),
        ('detail page: cell/tissue for a region',
         'SELECT "cell_tissue" FROM "TFBS_cell_or_tissue" WHERE "ID" = %s', [region_id]),
        ('autocomplete: TF names',
         'SELECT tfbs FROM tfbs_name_counts ORDER BY tfbs LIMIT 20', []),
        ('detail page: specific TF sites',
         '''SELECT d."tf_symbol", p."seqnames",
                   p."start" + e."site_start_off", p."start" + e."site_end_off",
                   bool_or(e."evidence" = 'b'), count(DISTINCT e."cell_id")
            FROM "tf_evidence" e
            JOIN "TFBS_position" p ON p."ID" = e."region_id"
            JOIN "tf_dictionary" d ON d."tf_id" = e."tf_id"
            WHERE e."region_id" = %s
            GROUP BY 1, 2, 3, 4''', [region_id]),
        ('cell/tissue list',
         'SELECT DISTINCT cell_tissue FROM "TFBS_cell_or_tissue" LIMIT 20', []),
    ]

    # Detail page annotations: one join per annotation type.
    joins = [
        ('enhancer', 'TFBS_to_enhancer', 'Enhancer_GB', 'enhancer_ID'),
        ('promoter', 'TFBS_to_promoter', 'Promoter', 'promoter_ID'),
        ('histone', 'TFBS_to_histone', 'histone', 'histone_ID'),
        ('cCREs', 'TFBS_to_cCREs', 'cCREs', 'cCREs_ID'),
        ('rE2G', 'TFBS_to_rE2G', 'rE2G', 'rE2G_ID'),
        ('TE', 'TFBS_to_TE', 'TE', 'TE_ID'),
        ('GWAS', 'TFBS_to_GWAS', 'GWAS', 'GWAS_ID'),
        ('eQTL', 'TFBS_to_eQTL', 'eQTL', 'eQTL_ID'),
        ('blacklist', 'TFBS_to_blacklist', 'blacklist', 'blacklist_ID'),
        ('variable_CpG', 'TFBS_to_variable_CpG', 'variable_CpG', 'variable_CpG_ID'),
        ('Cookbook_ChIP', 'TFBS_to_Cookbook_ChIP', 'Cookbook_ChIP', 'Cookbook_ChIP_ID'),
        ('Cookbook_GHT_SELEX', 'TFBS_to_Cookbook_GHT_SELEX', 'Cookbook_GHT_SELEX',
         'Cookbook_GHT_SELEX_ID'),
    ]
    for label, link, target, key in joins:
        checks.append((
            f'detail page: {label} overlap join',
            f'''SELECT t."seqnames", t."start", t."end"
                FROM "{link}" l JOIN "{target}" t ON l."{key}" = t."{key}"
                WHERE l."ID" = %s''', [region_id]))

    for label, sql, params in checks:
        try:
            cursor.execute(sql, params)
            cursor.fetchall()
            report.ok(label)
        except Exception as exc:
            cursor.execute('ROLLBACK')
            report.fail(f'{label}: {str(exc).splitlines()[0]}')

    print(f'    note  {regions:,} regions; largest TF is {tf}')


def check_django_tables(cursor, database, report):
    """The default alias holds Django's own tables; a reload wipes them."""
    print('  django tables (this database is the "default" alias)')
    cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    present = {row[0] for row in cursor.fetchall()}
    gone = [t for t in DJANGO_TABLES if t not in present]
    if gone:
        report.fail(f'missing {", ".join(gone)} -- run: python manage.py migrate')
    else:
        report.ok('django tables present')


def run(species, report):
    database = DB_NAMES[species]
    print(f'\n=== {species} ({database}) ===')
    conn = psycopg2.connect(dbname=database, **DB_CONFIG)
    conn.set_session(readonly=True, autocommit=True)
    cursor = conn.cursor()

    check_schema(cursor, report)
    check_enums(cursor, report)
    check_evidence_codes(cursor, report)
    check_indexes(cursor, report)
    check_queries(cursor, species, report)
    if database == 'tfbspedia_mouse':
        check_django_tables(cursor, database, report)

    cursor.close()
    conn.close()


def main():
    species_list = sys.argv[1:] or ['human', 'mouse']
    unknown = [s for s in species_list if s not in DB_NAMES]
    if unknown:
        sys.exit(f'unknown species: {", ".join(unknown)}')

    report = Report()
    for species in species_list:
        try:
            run(species, report)
        except psycopg2.Error as exc:
            report.fail(f'{species}: could not connect or query -- '
                        f'{str(exc).splitlines()[0]}')

    print('\n' + '=' * 60)
    if report.failures:
        print(f'FAILED: {len(report.failures)} problem(s)')
        for failure in report.failures:
            print(f'  - {failure}')
        sys.exit(1)
    print(f'PASSED{f" with {len(report.warnings)} warning(s)" if report.warnings else ""}')


if __name__ == '__main__':
    main()
