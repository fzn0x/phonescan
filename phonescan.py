#!/usr/bin/env python3
"""
phonescan - a small Python recreation of PhoneInfoga's five scanners.

Scanners:
  local         offline parsing with libphonenumber (country, carrier, line type, validity)
  numverify     checks the number via the Numverify API (apilayer)   [needs NUMVERIFY_API_KEY]
  googlesearch  runs Google search queries ("dorks") and shows how many results each has
                [needs SERPAPI_KEY, or GOOGLE_API_KEY + GOOGLECSE_CX; otherwise prints links]
  googlecse     lists the actual result pages through Google Custom Search
                [needs GOOGLE_API_KEY + GOOGLECSE_CX]
  ovh           checks OVH Telecom VoIP number ranges (FR, BE, UK, ES, CH only)

Usage:
  pip install phonenumbers requests
    python3 phonescan.py +15555550123
    python3 phonescan.py +15555550123 --only local,googlesearch
    python3 phonescan.py +15555550123 --links          # also print the Google links
    python3 phonescan.py +15555550123 --json > report.json

API keys are read from environment variables (or a .env file next to this script):
  NUMVERIFY_API_KEY   from https://apilayer.com/marketplace/number_verification-api
  SERPAPI_KEY         from https://serpapi.com (free plan available) - used for result counts
  GOOGLE_API_KEY      Google Custom Search JSON API key (closed to new customers,
  GOOGLECSE_CX        shutting down 2027-01-01) - used if you already have one
  COUNT_MAX           optional, max queries googlesearch counts per run (default 15)
  GOOGLECSE_MAX       optional, max queries googlecse sends per run (default 10)

Only scan numbers you own or have permission to investigate.
"""

import argparse
import json
import os
import sys
import urllib.parse
from pathlib import Path

try:
    import phonenumbers
    from phonenumbers import PhoneNumberFormat, PhoneNumberType, carrier, geocoder, timezone
except ImportError:
    sys.exit("Missing dependency: pip install phonenumbers requests")

try:
    import requests
except ImportError:
    requests = None


# --------------------------------------------------------------------------- helpers

def load_dotenv():
    env = Path(__file__).with_name(".env")
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Skip(Exception):
    """Raised when a scanner can't run (missing key, unsupported country...)."""


TYPE_NAMES = {v: k for k, v in vars(PhoneNumberType).items() if isinstance(v, int)}


class Number:
    def __init__(self, raw: str):
        try:
            self.parsed = phonenumbers.parse(raw if raw.startswith("+") else "+" + raw)
        except phonenumbers.NumberParseException as e:
            raise SystemExit(f"Can't parse number: {e}")
        p = self.parsed
        self.e164 = phonenumbers.format_number(p, PhoneNumberFormat.E164)          # +15555550123
        self.international = self.e164.lstrip("+")                                  # 15555550123
        self.international_fmt = phonenumbers.format_number(p, PhoneNumberFormat.INTERNATIONAL)
        self.local_fmt = phonenumbers.format_number(p, PhoneNumberFormat.NATIONAL)  # (555) 555-0123
        self.raw_local = "".join(c for c in self.local_fmt if c.isdigit())          # 5555550123
        self.country_code: int = p.country_code or 0
        self.region = phonenumbers.region_code_for_number(p) or ""


def http_get(url, **kw):
    if requests is None:
        raise Skip("requests not installed (pip install requests)")
    try:
        r = requests.get(url, timeout=20, **kw)
    except requests.RequestException as e:
        raise Skip(f"network error: {e.__class__.__name__}: {e}")
    return r


# --------------------------------------------------------------------------- search backends
#
# Each backend takes a query and returns Google's estimated total result count (int).
# It raises QuotaError when the key is invalid or out of quota, so we stop early.

class QuotaError(Exception):
    pass


def count_serpapi(query: str) -> int:
    r = http_get("https://serpapi.com/search.json",
                 params={"engine": "google", "q": query, "num": 10,
                         "api_key": os.environ["SERPAPI_KEY"]})
    data = r.json() if r.content else {}
    err = data.get("error", "")
    if "hasn't returned any results" in err:
        return 0
    if r.status_code in (401, 403, 429) or "run out of searches" in err or "Invalid API key" in err:
        raise QuotaError(err or f"HTTP {r.status_code}")
    if err:
        raise RuntimeError(err)
    total = data.get("search_information", {}).get("total_results")
    if total is None:  # some result pages omit the estimate; fall back to what's on page 1
        return len(data.get("organic_results", []))
    return int(total)


def cse_request(query: str, num: int):
    r = http_get("https://www.googleapis.com/customsearch/v1",
                 params={"key": os.environ["GOOGLE_API_KEY"],
                         "cx": os.environ["GOOGLECSE_CX"], "q": query, "num": num})
    if r.status_code in (400, 403, 429):
        raise QuotaError(f"HTTP {r.status_code}")
    r.raise_for_status()
    return r.json()


def count_cse(query: str) -> int:
    return int(cse_request(query, 1).get("searchInformation", {}).get("totalResults", 0))


def pick_counter():
    if os.environ.get("SERPAPI_KEY"):
        return "SerpApi", count_serpapi
    if os.environ.get("GOOGLE_API_KEY") and os.environ.get("GOOGLECSE_CX"):
        return "Google CSE", count_cse
    return None, None


# --------------------------------------------------------------------------- scanners

def scan_local(n: Number):
    p = n.parsed
    return {
        "valid": phonenumbers.is_valid_number(p),
        "possible": phonenumbers.is_possible_number(p),
        "e164": n.e164,
        "international": n.international_fmt,
        "local": n.local_fmt,
        "country_code": n.country_code,
        "country": f"{n.region} {geocoder.country_name_for_number(p, 'en')}".strip(),
        "location": geocoder.description_for_number(p, "en") or None,
        "carrier": carrier.name_for_number(p, "en") or None,
        "line_type": TYPE_NAMES.get(phonenumbers.number_type(p), "UNKNOWN"),
        "timezones": list(timezone.time_zones_for_number(p)),
    }


def scan_numverify(n: Number):
    key = os.environ.get("NUMVERIFY_API_KEY")
    if not key:
        raise Skip("set NUMVERIFY_API_KEY to enable")
    r = http_get(
        "https://api.apilayer.com/number_verification/validate",
        params={"number": n.international},
        headers={"apikey": key},
    )
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200:
        raise Skip(f"API returned HTTP {r.status_code}: {data.get('message') or r.text[:200]}")
    keep = ["valid", "number", "local_format", "international_format", "country_prefix",
            "country_code", "country_name", "location", "carrier", "line_type"]
    return {k: data.get(k) for k in keep}


def _or_text(*vals):
    return "(" + " OR ".join(f'intext:"{v}"' for v in vals) + ")"


def build_dorks(n: Number):
    intl, plus, local = n.international, n.e164, n.raw_local
    both = _or_text(intl, local)
    all3 = _or_text(intl, plus, local)

    disposable_sites = [
        "hs3x.com", "receive-sms-now.com", "smslisten.com", "smsnumbersonline.com",
        "freesmscode.com", "catchsms.com", "smstibo.com", "smsreceiving.com",
        "getfreesmsnumber.com", "sellaite.com", "receive-sms-online.info",
        "receivesmsonline.com", "receive-a-sms.com", "sms-receive.net",
        "receivefreesms.com", "receive-sms.com", "receivetxt.com", "freephonenum.com",
        "freesmsverification.com", "receive-sms-online.com", "smslive.co",
    ]
    reputation_sites = ["whosenumber.info", "findwhocallsme.com", "yellowpages.ca",
                        "phonenumbers.ie", "who-calledme.com", "usphonesearch.net",
                        "whocalled.us", "quinumero.info", "uk.popularphotolook.com"]
    individuals_sites = ["numinfo.net", "sync.me", "whocallsyou.de", "pastebin.com",
                         "whycall.me", "locatefamily.com", "spytox.com"]
    social_sites = ["facebook.com", "twitter.com", "x.com", "linkedin.com",
                    "instagram.com", "vk.com", "tiktok.com"]
    # Extra (not in the original): common region-specific sites where numbers get posted.
    indonesia_sites = ["olx.co.id", "kaskus.co.id", "tokopedia.com", "shopee.co.id",
                       "facebook.com/marketplace", "getcontact.com"]
    exts = ["doc", "docx", "odt", "pdf", "rtf", "sxw", "psw", "ppt", "pptx",
            "pps", "csv", "txt", "xls", "xlsx"]

    groups = {
        "social_media": [(s, f"site:{s} {all3}") for s in social_sites],
        "disposable_providers": [(s, f"site:{s} {both}") for s in disposable_sites],
        "reputation": [(s, f"site:{s} {all3}") for s in reputation_sites],
        "individuals": [(s, f"site:{s} {all3}") for s in individuals_sites],
        "general": [
            ("documents", "(" + " OR ".join(f"ext:{e}" for e in exts) + f") {all3}"),
            ("exact match, all formats", f'"{intl}" OR "{plus}" OR "{local}" OR "{n.local_fmt}"'),
        ],
    }
    if n.region == "ID":
        groups["indonesia_extra"] = [(s, f"site:{s} {all3}") for s in indonesia_sites]

    out = {}
    for g, items in groups.items():
        out[g] = [{"name": name, "dork": q,
                   "url": "https://www.google.com/search?q=" + urllib.parse.quote_plus(q)}
                  for name, q in items]
    return out


def priority_order(dorks):
    """Broadest queries first, so a small quota still covers the most ground."""
    return (dorks["general"] + dorks["social_media"] + dorks.get("indonesia_extra", [])
            + dorks["reputation"] + dorks["individuals"] + dorks["disposable_providers"])


def scan_googlesearch(n: Number):
    dorks = build_dorks(n)
    backend, counter = pick_counter()
    if counter is None:
        return {"backend": None, "groups": dorks}

    limit = int(os.environ.get("COUNT_MAX", "15"))
    stop_reason = None
    for i, d in enumerate(priority_order(dorks)):
        if i >= limit:
            stop_reason = stop_reason or f"COUNT_MAX={limit} reached"
            break
        try:
            d["count"] = counter(d["dork"])
        except QuotaError as e:
            stop_reason = f"{backend} key/quota problem: {e}"
            break
        except Skip as e:
            stop_reason = str(e)
            break
        except Exception as e:  # one bad query shouldn't kill the rest
            d["error"] = f"{e.__class__.__name__}: {e}"
    return {"backend": backend, "groups": dorks, "stopped": stop_reason}


def scan_googlecse(n: Number):
    if not (os.environ.get("GOOGLE_API_KEY") and os.environ.get("GOOGLECSE_CX")):
        raise Skip("set GOOGLE_API_KEY and GOOGLECSE_CX to enable")
    limit = int(os.environ.get("GOOGLECSE_MAX", "10"))
    ordered = priority_order(build_dorks(n))
    hits, queried, errors = [], 0, []
    for d in ordered[:limit]:
        queried += 1
        try:
            data = cse_request(d["dork"], 10)
        except QuotaError as e:
            errors.append(f"{d['name']}: {e}")
            break  # quota or key problem, stop burning requests
        except Exception as e:
            errors.append(f"{d['name']}: {e}")
            continue
        for item in data.get("items", []):
            hits.append({"query": d["name"], "title": item.get("title"),
                         "url": item.get("link"), "snippet": item.get("snippet")})
    return {"queries_sent": queried, "of_total": len(ordered),
            "results": hits, "errors": errors or None}


OVH_COUNTRIES = {33: "fr", 32: "be", 44: "gb", 34: "es", 41: "ch"}


def scan_ovh(n: Number):
    cc = OVH_COUNTRIES.get(n.country_code)
    if not cc:
        raise Skip(f"country code +{n.country_code} not covered by OVH (only +33 +32 +44 +34 +41)")
    r = http_get("https://api.ovh.com/1.0/telephony/number/detailedZones", params={"country": cc})
    if r.status_code != 200:
        raise Skip(f"OVH API returned HTTP {r.status_code}")
    wanted = n.raw_local[:6] + "xxxx"
    for z in r.json():
        if z.get("number") == wanted:
            return {"found": True, "number_range": z.get("number"),
                    "city": z.get("city"), "zip_code": z.get("zipCode")}
    return {"found": False, "number_range": wanted}


SCANNERS = {
    "local": scan_local,
    "numverify": scan_numverify,
    "googlesearch": scan_googlesearch,
    "googlecse": scan_googlecse,
    "ovh": scan_ovh,
}


# --------------------------------------------------------------------------- output

def print_googlesearch(data, show_links, c):
    B, G, Y, R, D, X = c
    backend = data["backend"]
    if backend is None:
        print(f"    {Y}No search API key set, so result counts aren't available.{X}")
        print(f"    {D}Set SERPAPI_KEY (or GOOGLE_API_KEY + GOOGLECSE_CX) to get counts.")
        print(f"    Until then, open these links yourself:{X}")
    else:
        print(f"    {D}counts from {backend} (Google's estimate){X}")

    total_hits = 0
    for group, items in data["groups"].items():
        print(f"    {group.replace('_', ' ').title()}:")
        for it in items:
            label = f"{it['name']:<26}"
            if backend is None:
                print(f"      {D}{label}{X} {it['url']}")
                continue
            if "count" in it:
                cnt = it["count"]
                total_hits += cnt
                col = R if cnt > 0 else G
                shown = f"{col}{cnt:>8,} result{'s' if cnt != 1 else ''}{X}"
            elif "error" in it:
                shown = f"{R}   error: {it['error']}{X}"
            else:
                shown = f"{D}  not counted{X}"
            line = f"      {label} {shown}"
            # always show the link when there's something to look at
            if show_links or it.get("count", 0) > 0:
                line += f"  {D}{it['url']}{X}"
            print(line)
    if backend is not None:
        if data.get("stopped"):
            print(f"    {Y}stopped early: {data['stopped']}{X}")
        verdict = (f"{G}no results on any counted query{X}" if total_hits == 0
                   else f"{R}{total_hits:,} results in total, check the links above{X}")
        print(f"    {B}summary:{X} {verdict}")


def print_report(n, results, show_links):
    B, G, Y, R, D, X = "\033[1m", "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[0m"
    if not sys.stdout.isatty():
        B = G = Y = R = D = X = ""
    c = (B, G, Y, R, D, X)
    print(f"{B}Scanning {n.international_fmt}{X}\n")
    for name, (status, data) in results.items():
        mark = {"ok": f"{G}✓{X}", "skipped": f"{Y}–{X}", "error": f"{R}✗{X}"}[status]
        print(f"{mark} {B}{name}{X}")
        if status != "ok":
            print(f"    {D}{data}{X}\n")
            continue
        if name == "googlesearch":
            print_googlesearch(data, show_links, c)
        elif name == "googlecse":
            print(f"    queries sent: {data['queries_sent']}/{data['of_total']}")
            if not data["results"]:
                print(f"    {G}no results found{X}")
            for h in data["results"]:
                print(f"    [{h['query']}] {h['title']}\n      {h['url']}")
            if data["errors"]:
                print(f"    {R}errors: {', '.join(data['errors'])}{X}")
        else:
            for k, v in data.items():
                print(f"    {k:<14} {v}")
        print()


def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description="PhoneInfoga-style phone number scanner")
    ap.add_argument("number", help="number in international format, e.g. +15555550123")
    ap.add_argument("--only", help="comma-separated scanners to run: " + ",".join(SCANNERS))
    ap.add_argument("--links", action="store_true",
                    help="show Google links next to every count (default: only when results > 0)")
    ap.add_argument("--json", action="store_true", help="print results as JSON")
    a = ap.parse_args()

    n = Number(a.number)
    wanted = [w.strip() for w in a.only.split(",")] if a.only else list(SCANNERS)
    results = {}
    for name in wanted:
        fn = SCANNERS.get(name)
        if not fn:
            sys.exit(f"unknown scanner: {name}")
        try:
            results[name] = ("ok", fn(n))
        except Skip as e:
            results[name] = ("skipped", str(e))
        except Exception as e:  # keep going if one scanner breaks
            results[name] = ("error", f"{e.__class__.__name__}: {e}")

    if a.json:
        print(json.dumps({k: {"status": s, "data": d} for k, (s, d) in results.items()},
                         indent=2, ensure_ascii=False))
    else:
        print_report(n, results, a.links)


if __name__ == "__main__":
    main()