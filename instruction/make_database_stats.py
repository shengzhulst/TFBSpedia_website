"""
Build the summary statistics shown by the "Database at a glance" section of the
home page.

The numbers are aggregates over tens of millions of rows, so they are computed
once here and written to

    staticfiles/documents/database_stats_{species}.json

which the home page reads (cached in-process, like the other files in that
directory).  Re-run after loading new data:

    python instruction/make_database_stats.py            # both species
    python instruction/make_database_stats.py human       # just one

Takes a couple of minutes for human, seconds for mouse.
"""

import json
import os
import sys
from datetime import date

import psycopg2

# Number of entries kept in each "top N" ranking.
TOP_N = 15

# Placeholders that sit in the name columns alongside real values.  They are the
# largest entries in their tables, so leaving them in would make every ranking
# open with a non-answer.  Counted separately instead, so the page can footnote
# them rather than silently dropping them.
PLACEHOLDER_TFS = {'UNKNOWN'}
PLACEHOLDER_CELL_TISSUES = {'MULTIPLE', 'UNKNOWN'}

OUTPUT_DIR = os.path.join('staticfiles', 'documents')

DB_NAMES = {'human': 'tfbspedia_human', 'mouse': 'tfbspedia_mouse'}

DB_CONFIG = dict(user='postgres', password='', host='localhost', port='5432')


def rows_to_series(rows):
    """Turn (label, value) tuples into the [{label, value}] the page expects."""
    return [{'label': str(label), 'value': int(value)} for label, value in rows]


def query(cursor, sql):
    cursor.execute(sql)
    return cursor.fetchall()


def build(species):
    print(f'[{species}] connecting to {DB_NAMES[species]}...')
    conn = psycopg2.connect(dbname=DB_NAMES[species], **DB_CONFIG)
    conn.set_session(readonly=True, autocommit=True)
    cursor = conn.cursor()

    print(f'[{species}] counting regions...')
    total_regions = query(cursor, 'SELECT count(*) FROM "TFBS_position"')[0][0]

    print(f'[{species}] regions per chromosome...')
    # Ordered by the chromosome enum, not by count: chromosomes have a natural
    # order and the chart keeps it.
    by_chromosome = query(cursor, '''
        SELECT "seqnames", count(*)
        FROM "TFBS_position"
        GROUP BY "seqnames"
        ORDER BY "seqnames"
    ''')

    print(f'[{species}] regions per assay...')
    # DISTINCT because a region can be reported by more than one assay, which is
    # also why these do not sum to total_regions.
    by_assay = query(cursor, '''
        SELECT "tech", count(DISTINCT "ID")
        FROM "TFBS_tech"
        GROUP BY "tech"
        ORDER BY 2 DESC
    ''')

    print(f'[{species}] regions per source database...')
    by_source = query(cursor, '''
        SELECT "source", count(DISTINCT "ID")
        FROM "TFBS_source"
        GROUP BY "source"
        ORDER BY 2 DESC
    ''')

    print(f'[{species}] confidence score distribution...')
    by_confidence = query(cursor, '''
        SELECT "confident_score", count(*)
        FROM "tfbs_confident_score"
        WHERE "confident_score" IS NOT NULL
        GROUP BY "confident_score"
        ORDER BY "confident_score"
    ''')

    print(f'[{species}] importance score distribution...')
    # Plotted beside the confidence scores, so both are counts of the same
    # regions on one axis -- the two scales differ in range (importance starts
    # below zero) and the chart shows the union of their values.
    by_importance = query(cursor, '''
        SELECT "importance_score", count(*)
        FROM "tfbs_importance_score"
        WHERE "importance_score" IS NOT NULL
        GROUP BY "importance_score"
        ORDER BY "importance_score"
    ''')

    print(f'[{species}] TF rankings...')
    tf_rows = query(cursor, '''
        SELECT "tfbs", "all_count"
        FROM "tfbs_name_counts"
        WHERE "all_count" IS NOT NULL
        ORDER BY "all_count" DESC
    ''')
    named_tfs = [(name, count) for name, count in tf_rows
                 if name not in PLACEHOLDER_TFS]
    unnamed_regions = sum(count for name, count in tf_rows
                          if name in PLACEHOLDER_TFS)

    print(f'[{species}] regions per cell tissue...')
    cell_tissue_rows = query(cursor, '''
        SELECT "cell_tissue", count(*)
        FROM "TFBS_cell_or_tissue"
        WHERE "cell_tissue" IS NOT NULL
        GROUP BY "cell_tissue"
        ORDER BY 2 DESC
    ''')
    named_cell_tissues = [(name, count) for name, count in cell_tissue_rows
                          if name not in PLACEHOLDER_CELL_TISSUES]

    cursor.close()
    conn.close()

    return {
        'species': species,
        'generated': date.today().isoformat(),
        'totals': {
            'regions': int(total_regions),
            'tfs': len(named_tfs),
            'cell_tissues': len(named_cell_tissues),
            'sources': len(by_source),
            'assays': len(by_assay),
            # Regions whose TF is recorded as UNKNOWN; footnoted on the page.
            'unnamed_regions': int(unnamed_regions),
        },
        'by_chromosome': rows_to_series(by_chromosome),
        'by_assay': rows_to_series(by_assay),
        'by_source': rows_to_series(by_source),
        'by_confidence': rows_to_series(by_confidence),
        'by_importance': rows_to_series(by_importance),
        'top_tfs_by_regions': rows_to_series(named_tfs[:TOP_N]),
        'top_cell_tissues_by_regions': rows_to_series(named_cell_tissues[:TOP_N]),
    }


def main():
    species_list = sys.argv[1:] or ['human', 'mouse']
    unknown = [s for s in species_list if s not in DB_NAMES]
    if unknown:
        sys.exit(f'unknown species: {", ".join(unknown)}')

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for species in species_list:
        stats = build(species)
        path = os.path.join(OUTPUT_DIR, f'database_stats_{species}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=1, sort_keys=True)
        totals = stats['totals']
        print(f'[{species}] wrote {path}: '
              f'{totals["regions"]:,} regions, {totals["tfs"]:,} TFs, '
              f'{totals["cell_tissues"]:,} cell lines/tissues')


if __name__ == '__main__':
    main()
