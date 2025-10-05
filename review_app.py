from __future__ import annotations
"""Minimal clean Job Review Web UI backend."""
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import os
import threading

import pandas as pd
from flask import Flask, jsonify, request, render_template

DATA_FILE = Path(__file__).parent / "jobs.csv"
BACKUP_DIR = Path(__file__).parent / "_backups"
BACKUP_DIR.mkdir(exist_ok=True)

ID_COL = "__row_id"
DESCRIPTION_FIELD = "description"

REQUIRED_COLUMNS_DEFAULTS = [
    ("decision", None),
    ("decision_reason", None),
    ("last_updated", None),
]

EDITABLE_TEXT_FIELDS = [
    "company","title","url","location","time_posted","num_applicants",
    "seniority_level","job_function","industries","employment_type","full_or_part_time","applied_date",
]

class JobsStore:
    def __init__(self, csv_path: Path):
        self.csv_path = csv_path
        self.lock = threading.RLock()
        self.df = self._load()

    def _load(self) -> pd.DataFrame:
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV not found: {self.csv_path}")
        df = pd.read_csv(self.csv_path)
        for col, default in REQUIRED_COLUMNS_DEFAULTS:
            if col not in df.columns:
                df[col] = default
        # Migration: convert legacy 'later' decisions to 'delete'
        if 'decision' in df.columns:
            try:
                df['decision'] = df['decision'].replace({'later': 'delete'})
            except Exception:
                pass
        # Ensure optional display/edit fields exist
        for opt_col in EDITABLE_TEXT_FIELDS:
            if opt_col not in df.columns:
                df[opt_col] = None
        # Ensure long-form application artifact fields exist (only shown in certain filters)
        for long_col in ["cover_letter", "cv"]:
            if long_col not in df.columns:
                df[long_col] = None
        if ID_COL not in df.columns:
            df[ID_COL] = range(len(df))
        if DESCRIPTION_FIELD not in df.columns:
            df[DESCRIPTION_FIELD] = None
        return df

    def save(self) -> None:
        with self.lock:
            # Create a single "previous save" backup (overwrite older previous ones)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            # Remove any older prev backups so only one remains after this
            try:
                for p in BACKUP_DIR.glob('jobs_prev_backup_*.csv'):
                    try: p.unlink()
                    except Exception: pass
            except Exception:
                pass
            backup = BACKUP_DIR / f"jobs_prev_backup_{ts}.csv"
            tmp = self.csv_path.with_suffix('.tmp')
            out_df = self.df.drop(columns=[ID_COL]) if ID_COL in self.df.columns else self.df
            out_df.to_csv(tmp, index=False)
            out_df.to_csv(backup, index=False)
            os.replace(tmp, self.csv_path)
            # Do not retain more than one prev backup; session backup handled separately.

    def get_row(self, row_id: int) -> Optional[Dict[str, Any]]:
        with self.lock:
            sub = self.df[self.df[ID_COL] == row_id]
            if sub.empty:
                return None
            return sub.iloc[0].to_dict()

    def update_row(self, row_id: int, updates: Dict[str, Any]) -> bool:
        with self.lock:
            idx_arr = self.df.index[self.df[ID_COL] == row_id]
            if len(idx_arr) == 0:
                return False
            idx = idx_arr[0]
            dirty = False
            for k, v in updates.items():
                if k not in self.df.columns:
                    continue
                if isinstance(v, str) and v.strip() == '':
                    v = None
                if self.df.at[idx, k] != v:
                    self.df.at[idx, k] = v
                    dirty = True
            if dirty:
                self.df.at[idx, 'last_updated'] = datetime.utcnow().isoformat(timespec='seconds')
            return True

    def set_decision(self, row_id: int, decision: Optional[str], reason: Optional[str]) -> bool:
        norm = decision.lower() if decision else None
        if norm and norm not in {"apply","reject","delete"}:
            return False
        with self.lock:
            idx_arr = self.df.index[self.df[ID_COL] == row_id]
            if len(idx_arr) == 0:
                return False
            idx = idx_arr[0]
            self.df.at[idx,'decision'] = norm
            if reason is not None:
                self.df.at[idx,'decision_reason'] = (reason or None)
            self.df.at[idx,'last_updated'] = datetime.utcnow().isoformat(timespec='seconds')
            return True

    def delete_row(self, row_id: int) -> bool:
        """Remove a row permanently from the in‑memory dataframe.

        IDs are not renumbered; the row simply disappears from future navigation / filters.
        Persistence occurs only when save() is explicitly called (or via API that opts in).
        """
        with self.lock:
            idx_arr = self.df.index[self.df[ID_COL] == row_id]
            if len(idx_arr) == 0:
                return False
            self.df = self.df.drop(index=idx_arr[0])
            return True

    def _filtered(self, mode: str) -> pd.DataFrame:
        df = self.df
        # Deleted rows are only visible in 'all'
        if mode != 'all':
            df = df[(df['decision'] != 'delete') | (df['decision'].isna())]
        if mode == 'pending':
            return df[(df['decision'].isna()) | (df['decision'] == '')]
        if mode == 'missing_desc':
            return df[(df[DESCRIPTION_FIELD].isna()) | (df[DESCRIPTION_FIELD] == '')]
        if mode == 'reject':
            return df[df['decision'] == 'reject']
        if mode == 'to_apply':
            cond_apply = df['decision'] == 'apply'
            cond_no_date = (df['applied_date'].isna()) | (df['applied_date'] == '') if 'applied_date' in df.columns else True
            return df[cond_apply & cond_no_date]
        if mode == 'applied':
            if 'applied_date' in df.columns:
                return df[(~df['applied_date'].isna()) & (df['applied_date'] != '')]
            return df.iloc[0:0]
        return df

    def nav(self, current_id: Optional[int], direction: int, mode: str) -> Optional[int]:
        with self.lock:
            df = self._filtered(mode)
            ids = df[ID_COL].tolist()
            if not ids:
                return None
            if current_id is None or current_id not in ids:
                return ids[0]
            pos = ids.index(current_id)
            new_pos = pos + direction
            if not (0 <= new_pos < len(ids)):
                return None
            return ids[new_pos]

    def stats(self) -> Dict[str, Any]:
        with self.lock:
            total = len(self.df)
            apply_ct = int((self.df['decision'] == 'apply').sum())
            reject_ct = int((self.df['decision'] == 'reject').sum())
            delete_ct = int((self.df['decision'] == 'delete').sum())
            pending_ct = int(((self.df['decision'].isna()) | (self.df['decision'] == '')).sum())
            missing_desc = 0
            if DESCRIPTION_FIELD in self.df.columns:
                missing_desc = int(self.df[DESCRIPTION_FIELD].isna().sum())
            return dict(total=total, apply=apply_ct, reject=reject_ct, delete=delete_ct,
                        pending=pending_ct, missing_description=missing_desc)

def create_session_backup(data_file: Path):
    """Create (and replace) a session startup backup of the current jobs.csv.

    Keeps only a single jobs_session_backup_* file. Invoked once per process start.
    """
    if not data_file.exists():
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Remove older session backups
    try:
        for p in BACKUP_DIR.glob('jobs_session_backup_*.csv'):
            try: p.unlink()
            except Exception: pass
    except Exception:
        pass
    session_backup = BACKUP_DIR / f"jobs_session_backup_{ts}.csv"
    try:
        session_backup.write_bytes(data_file.read_bytes())
    except Exception:
        pass


def serialize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (pd.Timestamp, datetime)):
            v = v.isoformat()
        if isinstance(v, float) and pd.isna(v):
            v = None
        out[k] = v
    out['_editable_fields'] = EDITABLE_TEXT_FIELDS + ([DESCRIPTION_FIELD] if DESCRIPTION_FIELD in row else [])
    return out


def create_app(store: JobsStore) -> Flask:
    app = Flask(__name__, template_folder='templates')

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/api/stats')
    def api_stats():
        return jsonify(store.stats())

    @app.get('/api/job/<int:row_id>')
    def api_get_job(row_id: int):
        row = store.get_row(row_id)
        if row is None:
            return jsonify({'error':'not found'}), 404
        return jsonify(serialize_row(row))

    @app.post('/api/job/<int:row_id>')
    def api_update_job(row_id: int):
        payload = request.json or {}
        updates = payload.get('updates', {})
        if not store.update_row(row_id, updates):
            return jsonify({'error':'not found'}), 404
        if 'decision' in updates:
            store.set_decision(row_id, updates.get('decision'), updates.get('decision_reason'))
        if payload.get('save'):
            store.save()
        return jsonify({'status':'ok'})

    @app.post('/api/decision/<int:row_id>')
    def api_decision(row_id: int):
        payload = request.json or {}
        if not store.set_decision(row_id, payload.get('decision'), payload.get('reason')):
            return jsonify({'error':'invalid or not found'}), 400
        return jsonify({'status':'ok'})

    @app.get('/api/nav')
    def api_nav():
        try:
            current_id = int(request.args.get('current','')) if request.args.get('current') else None
        except ValueError:
            current_id = None
        direction = request.args.get('dir','next')
        mode = request.args.get('filter','pending')
        dir_int = 1 if direction == 'next' else -1
        new_id = store.nav(current_id, dir_int, mode)
        return jsonify({'id': new_id})

    @app.post('/api/save')
    def api_save():
        store.save()
        return jsonify({'status':'saved'})

    @app.get('/api/filters')
    def api_filters():
        return jsonify({'filters':['pending','missing_desc','reject','to_apply','applied','all']})

    @app.post('/api/delete/<int:row_id>')
    def api_delete(row_id: int):
        """Delete a row and return an adjacent row id (next preference, else previous).

        Query param 'filter' is used to determine the navigation context.
        Body may include {"save": true} to persist immediately.
        Response: {status, next_id}
        """
        mode = request.args.get('filter','pending')
        # Determine candidate navigation targets BEFORE deletion
        next_id = store.nav(row_id, 1, mode)
        prev_id = store.nav(row_id, -1, mode)
        if not store.delete_row(row_id):
            return jsonify({'error':'not found'}), 404
        # Prefer next if it is not the deleted row; if next was the deleted row or None, fall back
        candidate = None
        if next_id is not None and next_id != row_id:
            candidate = next_id
        elif prev_id is not None and prev_id != row_id:
            candidate = prev_id
        payload = {'status':'deleted', 'next_id': candidate}
        try:
            body = request.get_json(silent=True) or {}
        except Exception:
            body = {}
        if body.get('save'):
            store.save()
            payload['persisted'] = True
        return jsonify(payload)

    @app.post('/api/shutdown')
    def api_shutdown():
        """Shutdown the development server. Intended for local single-user use only."""
        func = request.environ.get('werkzeug.server.shutdown')
        used = 'werkzeug' if func else 'os_exit'
        def _do():
            try:
                if func:
                    func()
                else:
                    # Fallback: hard exit (dev only)
                    os._exit(0)
            except Exception:
                os._exit(1)
        # Slight delay to allow response to be sent fully
        threading.Timer(0.15, _do).start()
        return jsonify({'status':'shutting_down','method': used})

    @app.get('/api/list')
    def api_list():
        mode = request.args.get('filter','pending')
        df = store._filtered(mode)  # using internal helper for consistency
        sort_col = request.args.get('sort_col')
        sort_dir = request.args.get('sort_dir','asc')
        if sort_col:
            # We allow sorting by __row_id or any column present
            try:
                asc = (sort_dir != 'desc')
                if sort_col == ID_COL:
                    if ID_COL not in df.columns:
                        df = df.assign(**{ID_COL: range(len(df))})
                    df = df.sort_values(ID_COL, ascending=asc, na_position='last', kind='mergesort')
                elif sort_col in df.columns:
                    df = df.sort_values(sort_col, ascending=asc, na_position='last', kind='mergesort')
            except Exception:
                pass  # Ignore sort errors silently
        rows = []
        if df.empty:
            return jsonify({'filter': mode, 'count': 0, 'columns': [], 'rows': [], 'sort_col': sort_col, 'sort_dir': sort_dir})
        # Order: __row_id then dataframe columns (if __row_id already there, avoid dup)
        columns = [ID_COL] + [c for c in df.columns if c != ID_COL]
        for i, r in df.iterrows():
            row = {}
            for c in columns:
                if c == ID_COL:
                    row[c] = int(r[ID_COL]) if ID_COL in r else int(i)
                else:
                    val = r[c]
                    if isinstance(val, float) and pd.isna(val):
                        val = None
                    row[c] = val
            rows.append(row)
        return jsonify({'filter': mode, 'count': len(rows), 'columns': columns, 'rows': rows, 'sort_col': sort_col, 'sort_dir': sort_dir})

    return app


def main():
    parser = argparse.ArgumentParser(description='Run Job Review Web UI')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--host', type=str, default='127.0.0.1')
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()

    store = JobsStore(DATA_FILE)
    # Create session backup once at startup
    create_session_backup(DATA_FILE)
    app = create_app(store)
    print(f"Loaded {len(store.df)} rows from {DATA_FILE}")
    print(f"Visit: http://{args.host}:{args.port}")
    if not args.no_open:
        try:
            import webbrowser
            webbrowser.open(f"http://{args.host}:{args.port}")
        except Exception:
            pass
    app.run(host=args.host, port=args.port, debug=True, use_reloader=False)


if __name__ == '__main__':
    main()
