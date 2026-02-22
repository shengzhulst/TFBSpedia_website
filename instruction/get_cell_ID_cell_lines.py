import psycopg2
import csv
import os
import multiprocessing
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

OUTPUT_DIR = "./TFBSpedia_django/staticfiles/documents/cell_lines_ID_mouse"

DB_CONFIG = dict(
    dbname="tfbspedia_mouse",
    user="postgres",
    password="",
    host="localhost",
    port="5432"
)


def write_tissue_file(args):
    """Worker function: write one CSV file for a cell tissue."""
    tissue_name, ids, output_dir = args
    safe_filename = tissue_name.replace(" ", "_").replace(",", "").replace("/", "_") + ".csv"
    file_path = os.path.join(output_dir, safe_filename)
    with open(file_path, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["ID"])
        writer.writerows([i] for i in ids)
    return tissue_name


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Single bulk query instead of one query per tissue
    print("Fetching all data in a single query...")
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute('SELECT cell_tissue, "ID" FROM "TFBS_cell_or_tissue";')

    tissue_ids = defaultdict(list)
    for cell_tissue, id_val in cursor.fetchall():
        if cell_tissue:
            tissue_ids[cell_tissue].append(id_val)

    cursor.close()
    conn.close()

    total = len(tissue_ids)
    print(f"Found {total} unique cell lines/tissues. Writing files with multiprocessing...")

    work_items = [(tissue, ids, OUTPUT_DIR) for tissue, ids in tissue_ids.items()]
    n_workers = 8

    completed = 0
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(write_tissue_file, item): item[0] for item in work_items}
        for future in as_completed(futures):
            future.result()  # re-raises any worker exception
            completed += 1
            if completed % 100 == 0 or completed == total:
                print(f"  {completed}/{total} files written...")

    print(f"Export complete! All {total} files saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
