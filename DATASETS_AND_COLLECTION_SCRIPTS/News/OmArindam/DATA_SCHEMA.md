# CSV and JSON data schema

The topic datasets in this directory use the same record structure. Each CSV
file is a table with one article or source entry per row. The converter writes
each CSV to a JSON file with the same base name; the JSON document is an array
of objects, one object per input row.

## Fields

| Field | Type | Description |
|---|---|---|
| `title` | string | Article or entry title. |
| `text` | string | Article body, summary, or descriptive text. Text may be in Odia or another language. |
| `date` | string | Date associated with the source entry. The value is kept as supplied by the source and may be a date or a date-time string. |
| `id` | string | Source-specific identifier for the entry. Keep it as a string to preserve formatting. |
| `url` | string | URL associated with the entry. |
| `author` | string | Author name when available; an empty string means no author was supplied. |
| `source_type` | string | Kind of entry, commonly `news_article` or `encyclopedia_article`. |
| `source` | string | Publisher, website, or source name. |
| `scraped_at` | string | Time the entry was collected, generally represented as an ISO 8601 timestamp. |
| `query` | string | Topic label or search query associated with collection. |

All values are exported as strings, including dates and identifiers. Empty CSV
cells remain empty strings (`""`) in JSON; they are not changed to `null`.
Non-ASCII text is preserved as UTF-8.

## Example JSON record

```json
[
  {
    "title": "Article title",
    "text": "Article content or summary",
    "date": "2024-01-02T10:30:00+00:00",
    "id": "publisher-12345",
    "url": "https://example.com/article",
    "author": "",
    "source_type": "news_article",
    "source": "Example Publisher",
    "scraped_at": "2024-01-03T08:15:00+00:00",
    "query": "Topic label"
  }
]
```

## Conversion

Run `python convert_csv_to_json.py` to convert every `*.csv` file in this
directory. To use a different directory, pass it as an argument:

```text
python convert_csv_to_json.py path\to\data
```

The corresponding `.json` file is written next to each CSV and overwritten if
it already exists. The script reads UTF-8 CSV files (including a UTF-8 BOM),
and reports an error if a data row has a different number of columns than the
header.
