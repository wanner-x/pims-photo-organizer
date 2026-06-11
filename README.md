# PIMS V1

PIMS V1 is a PC-hosted, NAS-centered photo organization system for large personal libraries.

## Local Run

1. Create a Python 3.11 virtual environment.
2. Install the package with `pip install -e .[dev]`.
3. Mount or map NAS libraries before starting the app.
4. Start the API with `uvicorn pims_v1.main:app --reload`.
5. Run tests with `python -m pytest -v`.
