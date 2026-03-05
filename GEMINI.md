# Happy SAR Analyzer (sarfile_analyzer_ng)

A Streamlit-based web application for the graphical analysis and presentation of Linux `sar` (System Activity Reporter) files. It is a modern fork of the original `sar_file_analyzer`, optimized for performance using Polars and high-quality visualizations with Bokeh and Altair.

## Project Overview

- **Purpose**: Analyze Linux `sar` files (ASCII format) and generate interactive charts for various metrics (CPU, Memory, Disk, Network, etc.).
- **Main Technologies**:
    - **Frontend**: [Streamlit](https://streamlit.io/) for the web interface.
    - **Data Processing**: [Polars](https://pola.rs/) for efficient data manipulation, [Pandas](https://pandas.pydata.org/) for interoperability.
    - **Visualization**: [Bokeh](https://docs.bokeh.org/) for high-performance interactive charts, [Altair](https://altair-viz.github.io/) for declarative statistical visualizations.
    - **Database**: [SQLite](https://www.sqlite.org/) with [SQLAlchemy](https://www.sqlalchemy.org/) for user management and metric metadata.
    - **Caching**: [Redis](https://redis.io/) for storing parsed Parquet data to speed up repeated access.
    - **Environment**: Python 3.11/3.12.

## Directory Structure

- `code/`: Contains all Python source files and application assets.
    - `start_sar_analyzer.py`: The main entry point for the Streamlit application.
    - `parse_into_polars.py`: Core logic for parsing ASCII `sar` files into Polars DataFrames.
    - `bokeh_charts.py`: Advanced chart generation module using Bokeh.
    - `sql_stuff.py`: Handles database schema (Users, Roles, Metrics, Headings).
    - `config.py`: Application configuration using environment variables.
    - `redis_mng.py`: Redis client management for caching.
    - `.streamlit/`: Streamlit-specific configuration (`config.toml`).
- `docker/`: Contains the `Dockerfile` based on SUSE Linux Enterprise 15 SP6.
- `deployment/`: Kubernetes/YAML files for deployment.

## Building and Running

### Local Development
1. **Navigate to the code directory**:
   ```bash
   cd code
   ```
2. **Create and activate a virtual environment**:
   ```bash
   python3.12 -m venv venv
   source venv/bin/activate
   ```
3. **Install dependencies**:
   ```bash
   pip install -U pip
   pip install -r requirements.txt
   ```
4. **Run the application**:
   ```bash
   streamlit run start_sar_analyzer.py
   ```

### Using Docker
```bash
docker build -f docker/Dockerfile -t happy-sar-analyzer .
docker run -p 8501:8501 happy-sar-analyzer
```

## Key Components & Workflow

1. **Authentication**: Users can sign up and log in. Roles (`admin`, `user`) define access to management features.
2. **File Management**: Users upload ASCII `sar` files via "Manage Sar Files". Files are stored in `code/upload/<username>/`.
3. **Parsing & Caching**:
    - Uploaded files are parsed into Polars DataFrames.
    - Parsed data is saved as `.parquet` files and cached in Redis for high-speed retrieval.
4. **Analysis Modes**:
    - **Graphical Overview**: Quick look at multiple metrics.
    - **Detailed Metrics View**: Drill down into specific metrics.
    - **Multiple Sar Files**: Compare different `sar` files.
    - **Metrics on many devices**: Visualize metrics across multiple sub-devices (e.g., individual CPUs).

## Configuration

Configuration is managed via `code/config.py` and environment variables:
- `UPLOAD_DIR`: Directory for uploaded files (default: `upload`).
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`: Redis connection details.
- `DEBUG`: Enable/disable debug mode (default: `True`).
- `MAX_METRIC_HEADER`: Limits for UI rendering.

Streamlit server settings are in `code/.streamlit/config.toml`.

## Performance & Stability Notes

- **Redis-Regression (7.2.1)**: Die Version `redis-py 7.2.1` hat auf macOS/Darwin eine massive Verzögerung (Faktor 100) beim Starten der App verursacht, wenn kein Redis-Server läuft. Dies betrifft besonders die Phasen `aliases + selection diff` und `render.metric_popover`. 
- **Fix**: Das Paket `redis` ist in `requirements.txt` fest auf Version **7.1.0** gepinnt. Andere Bibliotheken (Polars, Numpy etc.) funktionieren performant in ihren neuesten Versionen.
- **Datenbank-Suche**: Die Funktion `find_db()` in `sql_stuff.py` wurde optimiert, um rekursive Scans (`os.walk`) des Projekts (insb. `venv/`) zu vermeiden. Dies verhindert 15+ Sekunden Latenz bei jedem Datenbank-Lookup.
- **Concurrency**: Parallelisierung in `dia_overview_pl.py` wurde optimiert (Pre-Calculation von Metadaten im Main-Thread), um den globalen Cache-Lock von Streamlits `@cache_data` innerhalb von Threads zu umgehen.

