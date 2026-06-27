# Spider dataset (not committed)

The Spider text-to-SQL benchmark lives here after download. It is gitignored
because the SQLite bundle is ~100MB.

First-time setup:

```bash
pip install gdown
python scripts/import_spider.py
```

This downloads the dataset (community mirror of the official Yale release),
verifies all dev gold queries execute, and writes `data/problems/sql.json`.

Source: [Spider (Yale LILY)](https://yale-lily.github.io/spider) — CC BY-SA 4.0
