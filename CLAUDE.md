# sarfile_analyzer_ng

Linux sar file analyzer: Streamlit app (`code/`, entry `start_sar_analyzer.py`),
REST API `/api/v1` (`api/`), MCP server (`mcp_server/`), lab deployment
(`deployment/lab/`, German README). The web frontend
jschaef/sarfile_analyzer_web imports `code/` and `api/` from here. Full
background, pitfalls and the lab setup: [`docs/knowledge.md`](docs/knowledge.md)
– read it before larger changes.

## Working rules (Jochen)

- Talk to Jochen in German; code, comments and commit messages in English;
  PR descriptions and lab docs in German.
- Change this repo only when Jochen asks for it. Commit on the session
  branch with `--author="Jochen Schäfer <jochen.schaefer@suse.com>"`, no
  `Co-Authored-By` trailer, end with the `Claude-Session:` line.
- Never push to `main`, never merge – Jochen merges himself.
- Small topic commits, only after the change is checked.
- `code/data.db` in git is the seed (admin/password, roles, headings,
  metrics). Never commit real users; experiment on a copy. No real sar files
  in git.

## Checking a change

There are no tests or CI in this repo. Instead:

- import/syntax check in the venv (`python -c 'import config'` in `code/`)
- run Streamlit from a copy of `code/` (it then uses the copied `data.db`)
  with its own `UPLOAD_DIR` and `REDIS_ENABLED=false`
- run sarfile_analyzer_web's `backend/` pytest suite against this checkout
- `git diff --quiet HEAD -- code/data.db` afterwards

## Pitfalls

- sarfile_analyzer_web uses `sql_stuff`, `config`, `sqlite2_polars`,
  `handle_user_status`, `validation`, `api/services.py` (including private
  helpers like `_parse_bound`) – renaming breaks it.
- Settings belong in `config.EDITABLE_SETTINGS` / `settings.json`, never in
  a patched `config.py`; they apply without restart via the file's mtime.
- `$UPLOAD_DIR/config/` is shared state of all processes; the username
  `config` is reserved. Write files there atomically.
- Streamlit reruns the main script in a fresh namespace: once-per-process
  guards belong in imported modules.
- On the lab server `code/data.db` is skip-worktree protected (real users);
  `deploy.sh` does not restart Streamlit.
- `mcp` must stay `<2` (2.x removed `mcp.server.fastmcp`).
