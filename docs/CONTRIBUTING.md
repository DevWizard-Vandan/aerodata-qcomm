# Contributing Guidelines

Thank you for contributing to `aerodata-qcomm`! This repository provides institutional-grade alternative data pipelines and quantitative signal modules.

---

## Code of Conduct & Standards

- **Strict Production Mode (`STRICT_PROD_MODE`)**: Do not add silent `try/except` fallbacks or fake dummy data returns to production scraper paths. When endpoints fail, raise explicit `ScraperHTTPError`, `RateLimitError`, or `ScraperParsingError` and emit structured JSON error telemetry.
- **Data Guardrails**: Any new field or metric added to the ingest payload must be supported by `signals/data_guardrails.py` to prevent corrupt data insertion into database tables.
- **Code Style**: Follow PEP 8 guidelines for Python code. Maintain clear type hints on public methods.

---

## Local Development Workflow

1. **Fork & Clone**:
   ```bash
   git clone https://github.com/DevWizard-Vandan/aerodata-qcomm.git
   cd aerodata-qcomm
   ```

2. **Setup Virtual Environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   # .venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   ```

3. **Run Diagnostic Connection Checks**:
   ```bash
   python scrapers/test_connection.py --url https://api.zepto.com/api/v1/get_page
   ```

4. **Run Ingestion in Dev Mode**:
   ```bash
   STRICT_PROD_MODE=false python main.py
   ```

5. **Commit & Push**:
   Use descriptive commit messages prefixed with standard conventional tags:
   - `feat:` New feature or scraper connector
   - `fix:` Bug fix or path resolution fix
   - `refactor:` Code refactoring without behavioral change
   - `docs:` Documentation improvements

---

## Opening Pull Requests

1. Rebase your branch over `origin/main` before submitting:
   ```bash
   git pull --rebase origin main
   ```
2. Open a Pull Request on GitHub describing the changes made, verification steps completed, and logs attached.
