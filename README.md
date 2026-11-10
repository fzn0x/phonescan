# phonescan

A small Python information-gathering tool for phone numbers, built from five independent scanners.

It tells you basic facts about a number (country, carrier, line type, validity) and generates search queries that show where the number appears publicly online. It's meant for checking your own number's exposure, or numbers you have permission to investigate.

## What it does

| Scanner        | What it does                                                                                                                                                                                                                                                                                       | Needs                                                  |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| `local`        | Offline parsing with libphonenumber: validity, formats, country, carrier, line type, time zone                                                                                                                                                                                                     | Nothing                                                |
| `numverify`    | Checks the number against the Numverify API (apilayer): whether it's valid, carrier, line type                                                                                                                                                                                                     | `NUMVERIFY_API_KEY`                                    |
| `googlesearch` | Runs Google searches ("dorks") across social media, disposable SMS sites, reputation/spam sites, people-finder sites and leaked documents, and shows **how many results** each one has. Adds extra region-specific sites for some country codes. Without a key, it prints the search links instead | `SERPAPI_KEY` (or `GOOGLE_API_KEY` + `GOOGLECSE_CX`)   |
| `googlecse`    | Lists the actual result pages (title and URL) through Google's Custom Search API                                                                                                                                                                                                                   | `GOOGLE_API_KEY`, `GOOGLECSE_CX`                       |
| `ovh`          | Checks whether the number falls in an OVH Telecom VoIP range                                                                                                                                                                                                                                       | Nothing (France, Belgium, UK, Spain, Switzerland only) |

Scanners without the required key or country are skipped, and the rest still run.

**What it doesn't do:** it can't track a phone, find its location, identify the owner by itself, or access the phone in any way. The carrier is guessed from the number prefix, so it may be wrong if the number was ported to another provider.

## Installation

Requires Python 3.8 or newer.

```bash
git clone <your-repo-url> phonescan    # or just download phonescan.py and requirements.txt
cd phonescan
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt`:

```
phonenumbers>=8.13
requests>=2.28
```

## Optional: API keys

Create a `.env` file next to `phonescan.py` (or export the variables in your shell):

```
NUMVERIFY_API_KEY=your_apilayer_key
SERPAPI_KEY=your_serpapi_key
COUNT_MAX=15

# Only if you already have Google Custom Search access:
GOOGLE_API_KEY=your_google_cloud_key
GOOGLECSE_CX=your_search_engine_id
GOOGLECSE_MAX=10
```

- **NUMVERIFY_API_KEY**: sign up at apilayer.com and subscribe to the free _Number Verification API_ plan.
- **SERPAPI_KEY**: sign up at serpapi.com (there's a free plan) and copy your API key from the dashboard. This is what gives `googlesearch` its result counts. Each counted query uses one search from your plan.
- **COUNT_MAX** (optional): how many queries `googlesearch` counts per run. The default is 15, out of about 51 queries total. The broadest queries are counted first; the rest show as "not counted". Raise it if your plan allows.
- **GOOGLE_API_KEY** / **GOOGLECSE_CX**: Google's Custom Search JSON API is closed to new customers and shuts down on January 1, 2027. If you already have a key, `googlesearch` uses it for counts when `SERPAPI_KEY` isn't set, and `googlecse` uses it to list result pages.
- **GOOGLECSE_MAX** (optional): how many queries `googlecse` sends per run. The default is 10.

### How to obtain each key

#### 1) `NUMVERIFY_API_KEY` (apilayer)

1. Open <https://apilayer.com> and create an account (or sign in).
2. Search for **Number Verification API** and open its product page.
3. Subscribe to a plan (free plan is usually enough to start).
4. Go to your apilayer dashboard and copy your API key.
5. Put it in `.env`:

```env
NUMVERIFY_API_KEY=your_real_apilayer_key
```

Quick check:

```bash
python phonescan.py +15555550123 --only numverify
```

If the key works, `numverify` will run instead of showing "set NUMVERIFY_API_KEY to enable".

#### 2) `SERPAPI_KEY` (SerpApi)

1. Open <https://serpapi.com> and create an account (or sign in).
2. In the dashboard, open the API key page (often labeled **API Key**).
3. Copy your key.
4. Put it in `.env`:

```env
SERPAPI_KEY=your_real_serpapi_key
```

Quick check:

```bash
python phonescan.py +15555550123 --only googlesearch
```

If the key works, `googlesearch` shows result counts instead of only links.

Notes:

- Each counted query consumes search quota from your SerpApi plan.
- Use `COUNT_MAX` to control usage per run:

```env
COUNT_MAX=15
```

#### 3) `GOOGLE_API_KEY` and `GOOGLECSE_CX` (legacy users only)

Google's Custom Search JSON API is closed to new customers and shuts down on January 1, 2027. These steps are only for users who already have access.

Get `GOOGLE_API_KEY`:

1. Open <https://console.cloud.google.com> and select your existing project.
2. Confirm **Custom Search API** is already enabled for that project.
3. Go to **APIs & Services** -> **Credentials**.
4. Create or copy an existing API key.
5. Put it in `.env`:

```env
GOOGLE_API_KEY=your_real_google_api_key
```

Get `GOOGLECSE_CX` (Search Engine ID):

1. Open <https://programmablesearchengine.google.com>.
2. Open your existing programmable search engine.
3. Copy the **Search engine ID** (also called `cx`).
4. Put it in `.env`:

```env
GOOGLECSE_CX=your_search_engine_id
```

Optional limit:

```env
GOOGLECSE_MAX=10
```

Quick check:

```bash
python phonescan.py +15555550123 --only googlecse
```

If credentials are valid, `googlecse` will list result pages (title + URL).

Don't commit `.env` to git. Add it to `.gitignore`.

## Usage

Numbers must be in international format (with or without the leading `+`).

```bash
# Run all scanners
python3 phonescan.py +15555550123

# Run only some scanners
python3 phonescan.py +15555550123 --only local,googlesearch

# Show the Google link next to every count (by default, links only appear for queries with results)
python3 phonescan.py +15555550123 --links

# Save results as JSON
python3 phonescan.py +15555550123 --json > report.json

# Help
python3 phonescan.py --help
```

On Windows, use `python` instead of `python3`.

### Example output (shortened)

```
Scanning +1 555-555-0123

✓ local
    valid          True
    country        US
    carrier        Example Carrier
    line_type      MOBILE
    timezones      ['Example/Timezone']

– numverify
    set NUMVERIFY_API_KEY to enable

✓ googlesearch
    counts from SerpApi (Google's estimate)
    Social Media:
      facebook.com                      0 results
      instagram.com                     0 results
      ...
    Disposable Providers:
      hs3x.com                     not counted
      ...
    General:
      documents                         0 results
      exact match, all formats          3 results  https://www.google.com/search?q=...
    summary: 3 results in total, check the links above

– googlecse
    set GOOGLE_API_KEY and GOOGLECSE_CX to enable

– ovh
  country code +1 not covered by OVH (only +33 +32 +44 +34 +41)
```

`✓` means the scanner ran, `–` means it was skipped, and `✗` means it hit an error.

Without `SERPAPI_KEY` (or a Google CSE key), `googlesearch` prints each query's Google link instead of a count, so you can open them yourself.

### Reading the results

- **0 results** everywhere is the good outcome: the number doesn't show up publicly in those places.
- Counts are **Google's estimates**. They can be rough for small numbers, so open the link for any query with results and check that the page really contains the number.
- "**not counted**" means the query was skipped because of `COUNT_MAX` or quota. Raise `COUNT_MAX` or run `--links` to check those yourself.
- Hits on **disposable providers** mean the number has been listed as a public SMS-receiving number.
- Hits on **reputation** sites usually mean someone reported the number as spam or a scam.

## Differences from PhoneInfoga

- One Python file instead of a Go program; no web interface or REST API.
- Adds x.com, TikTok, and extra region-specific groups to the searches.
- `googlesearch` shows result counts per query (via SerpApi or Google CSE) instead of only links.
- Counting and `googlecse` run the broadest queries first and stop on quota errors.

## Disclaimer

Only scan numbers you own or have permission to investigate. Results come from public sources and third-party APIs and may be incomplete or wrong.

## License

MIT. See LICENSE.

## Contributing

See CONTRIBUTING.md.

## Security

See SECURITY.md for responsible disclosure guidance.
