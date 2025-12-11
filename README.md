# ScrapeDocs

A Python script to scrape documentation sites into Markdown.

## Usage

1. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the script:
   ```bash
   python3 scrapedocs.py --url "https://docs.example.com"
   ```

### Custom Output Directory

You can specify a custom name for the run directory:

```bash
# Creates output/my-custom-name/
python3 scrapedocs.py --run-name "my-custom-name"

# Creates output/YYYYMMDD_HHMMSS_my-custom-name/
python3 scrapedocs.py --run-name "my-custom-name" --append-to-timestamp
```

## Output

Output files (Markdown and images) are saved to a timestamped subdirectory within the `output/` directory (e.g., `output/20251211_231614/`).