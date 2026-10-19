"""The six notebooks a second time, as marimo notebooks, exported to docs/notebooks/ as the static notebook site.

Same cells as the Snowflake notebooks: each markdown cell becomes mo.md, each SQL cell becomes mo.sql run on one
Snowflake connection (the `whales` connection, with the warehouse and the MARTS schema set on it). Exporting runs
every cell once and saves the results in the page, so the site needs no database and runs nothing in the browser.
The marimo files themselves are a step on the way and are not kept in git.
"""
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BUILD = HERE / 'build'
SITE = ROOT / 'docs' / 'notebooks'

CONNECT = '''\
# One Snowflake session for the whole notebook: the warehouse that runs the queries and the schema dbt builds
# the star in. Temporary views made in one cell stay visible to the cells after it.
import snowflake.connector

snowflake_session = snowflake.connector.connect(
    connection_name="whales", warehouse="WHALES_WH", database="WHALES", schema="MARTS"
)'''


def _text(cell):
    return ''.join(cell['source'])


def _title(cells):
    return next(line[2:].strip() for line in _text(cells[0]).split('\n') if line.startswith('# '))


def _nav(i, stems):
    def link(j, label):
        return f'<a class="wh-btn" href="{stems[j]}.html">{label}</a>'
    prev = link(i - 1, f'← Previous: {i:02d}') if i > 0 else ''
    nxt = link(i + 1, f'Next: {i + 2:02d} →') if i < len(stems) - 1 else ''
    return ('<header class="wh-top"><a class="wh-brand" data-portfolio="home">Brandon Connely</a>'
            '<nav class="wh-nav"><a class="wh-btn" href="../index.html">All Notebooks</a>'
            f'{prev}{nxt}<a class="wh-btn wh-case" data-portfolio="case">Case Study</a></nav></header>')


def _md_cell(text):
    return f'@app.cell(hide_code=True)\ndef _(mo):\n    mo.md(r"""\n{textwrap.indent(text, "    ")}\n    """)\n    return\n'


def _sql_cell(name, query):
    """The query as a SQL cell, then its result in full: a static page keeps only the rows a table shows."""
    body = textwrap.indent(query, '        ')
    shown = '' if query.lstrip().upper().startswith('CREATE') else (
        f'\n\n@app.cell(hide_code=True)\ndef _(mo, {name}):\n'
        f'    mo.ui.table({name}, page_size=50, selection=None, show_download=False)\n    return\n')
    return (f'@app.cell\ndef _(mo, snowflake_session):\n'
            f'    {name} = mo.sql(\n        f"""\n{body}\n        """,\n        engine=snowflake_session,\n'
            f'        output=False,\n    )\n    return ({name},)\n{shown}')


def write_all(notebooks):
    """notebooks: [(filename, cells)] in order, as nb.write received them."""
    stems = [Path(f).stem for f, _ in notebooks]
    titles = [_title(cells) for _, cells in notebooks]
    for i, (filename, cells) in enumerate(notebooks):
        parts = [
            'import marimo\n\n__generated_with = "0.25.1"\n'
            f'app = marimo.App(\n    width="medium",\n    app_title="{i + 1:02d} · {titles[i]}",\n'
            '    css_file="../site.css",\n    html_head_file="../head.html",\n    sql_output="pandas",\n)\n',
            '@app.cell(hide_code=True)\ndef _():\n    import marimo as mo\n    return (mo,)\n',
            _md_cell(_nav(i, stems)),
        ]
        intro = _text(cells[0]).replace('# ' + titles[i], f'<p class="wh-kicker">Notebook {i + 1:02d} of '
                                        f'{len(notebooks):02d}</p>\n\n# {titles[i]}', 1)
        parts.append(_md_cell(intro))
        parts.append(f'@app.cell\ndef _():\n{textwrap.indent(CONNECT, "    ")}\n    return (snowflake_session,)\n')
        for cell in cells[1:]:
            name = cell['metadata']['name']
            if cell['cell_type'] == 'markdown':
                parts.append(_md_cell(_text(cell)))
            else:
                parts.append(_sql_cell(name, _text(cell).removeprefix('%%sql\n')))
        parts.append('if __name__ == "__main__":\n    app.run()\n')
        BUILD.mkdir(exist_ok=True)
        (BUILD / f'{stems[i]}.py').write_text('\n\n'.join(parts), encoding='utf-8')


def export_all(notebooks):
    """Run each marimo notebook against Snowflake and save it as a static page in docs/notebooks/."""
    shutil.rmtree(SITE, ignore_errors=True)
    SITE.mkdir(parents=True)
    for filename, _ in notebooks:
        stem = Path(filename).stem
        subprocess.run([sys.executable, '-m', 'marimo', 'export', 'html', f'build/{stem}.py', '-o', str(SITE / f'{stem}.html'),
                        '--include-code', '--force'], cwd=HERE, check=True)
        print('exported docs/notebooks/' + stem + '.html')
