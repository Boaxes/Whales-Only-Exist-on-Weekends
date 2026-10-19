"""Write the analysis notebooks from code: md() and sql() cells -> .ipynb, one notebook per claim.

The notebooks are Snowflake Notebooks in Workspaces with SQL cells only (each starts with the `%%sql` cell
magic): markdown says what each step asks, SQL answers it against the star in WHALES.MARTS.
`python analysis/notebooks_src/build.py` writes them to analysis/, and the static marimo pages to docs/notebooks/.
"""
import json
import textwrap
from pathlib import Path

ANALYSIS = Path(__file__).resolve().parent.parent


def _lines(text):
    lines = textwrap.dedent(text).strip('\n').split('\n')
    return [line + '\n' for line in lines[:-1]] + [lines[-1]]


def md(name, text):
    return {'cell_type': 'markdown', 'metadata': {'name': name, 'collapsed': False}, 'source': _lines(text)}


def sql(name, query):
    return {'cell_type': 'code', 'metadata': {'name': name, 'language': 'sql', 'collapsed': False},
            'execution_count': None, 'outputs': [], 'source': _lines('%%sql\n' + textwrap.dedent(query).strip('\n'))}


def write(filename, cells):
    # (a Workspace notebook starts with no warehouse and no database: the first two SQL cells set them, for the
    # queries and temporary views; one statement per cell)
    setup = [sql('warehouse', '-- WHALES_WH runs the queries.\nUSE WAREHOUSE whales_wh'),
             sql('setup', '-- The star dbt builds lives in WHALES.MARTS.\nUSE SCHEMA whales.marts')]
    cells = cells[:1] + setup + cells[1:]
    nb = {'cells': cells,
          'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                       'language_info': {'name': 'python'}},
          'nbformat': 4, 'nbformat_minor': 5}
    for i, c in enumerate(cells):
        c['id'] = f'{c["metadata"]["name"]}-{i}'
    (ANALYSIS / filename).write_text(json.dumps(nb, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print('wrote', filename, len(cells), 'cells')
