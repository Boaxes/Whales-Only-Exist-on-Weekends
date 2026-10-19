"""Title and link for every dataset in RAW.OBIS_OCCURRENCE, from the OBIS API, into RAW.OBIS_DATASET.

Run after 02_obis.sql:  uv run python load/04_datasets.py
The API's dataset search no longer returns many of these datasets, but looking each one up by id still works.
Each dataset's licence and citation are in its API record (make_credits.py reads them).
"""
import json
import urllib.request

import snowflake.connector

con = snowflake.connector.connect(connection_name='whales')
cur = con.cursor()
ids = [r[0] for r in cur.execute('SELECT DISTINCT dataset_id FROM WHALES.RAW.OBIS_OCCURRENCE ORDER BY dataset_id')]

rows = []
for i in ids:
    with urllib.request.urlopen(f'https://api.obis.org/v3/dataset/{i}', timeout=60) as r:
        found = json.load(r)['results']
    d = found[0] if found else {}
    rows.append((i, d.get('title'), d.get('url'), json.dumps(d)))
print(len(ids), 'datasets,', sum(1 for r in rows if r[1] is None), 'not found in the API')

cur.execute('''CREATE OR REPLACE TABLE WHALES.RAW.OBIS_DATASET (
    dataset_id STRING, title STRING, url STRING, api_record VARIANT,
    _loaded_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP())''')
cur.execute('CREATE OR REPLACE TEMPORARY TABLE OBIS_DATASET_LOAD (dataset_id STRING, title STRING, url STRING, api_record STRING)')
cur.executemany('INSERT INTO OBIS_DATASET_LOAD VALUES (%s, %s, %s, %s)', rows)
cur.execute('''INSERT INTO WHALES.RAW.OBIS_DATASET (dataset_id, title, url, api_record)
    SELECT dataset_id, title, url, PARSE_JSON(api_record) FROM OBIS_DATASET_LOAD''')
print(cur.execute('SELECT COUNT(*) FROM WHALES.RAW.OBIS_DATASET').fetchone()[0], 'rows in RAW.OBIS_DATASET')
