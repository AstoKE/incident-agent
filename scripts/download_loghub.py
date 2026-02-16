from __future__ import annotations

import argparse
import os 
import re
import sys
import urllib.request
from pathlib import Path  
from typing import Dict, Any, Tuple, Optional

LOGHUB_README_RAW = "https://raw.githubusercontent.com/logpai/loghub/master/README.md"
DEFAULT_OUT_DIR = Path("data") / "loghub"

def http_get_text(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent":"incident-agent-loghub-downloader/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")
    

def http_download(url: str, out_path: Path, timeout: int=60) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    req= urllib.request.Request(url, headers={"User-Agent": "incident-agent-loghub-downloader/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(out_path, "wb")as f:
        while True:
            chunk=resp.read(1024*1024)
            if not chunk:
                break
            f.write(chunk)


def parse_dataset_links(readme_md: str) -> Dict[str, str]:
    
    out: Dict[str, str] = {}

    pattern = re.compile(
        r"\[([A-Za-z0-9_]+)\]\([^)]+\)\s*.*?\[:link:\]\((https?://[^)]+)\)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    for m in pattern.finditer(readme_md):
        name = m.group(1).strip()
        url = m.group(2).strip()
        out[name] = url

    return out



def normalize_url(url: str) -> str:
    url = url.strip()

    if url.startswith("http://" or url.startswith("https://")):
        return url
    
    url = url.lstrip("./")

    return f"https://raw.githubusercontent.com/logpai/loghub/master/{url}"


def choose_output_filename(dataset: str, url: str) -> str:

    base = url.split("?")[0].rstrip("/").split("/")[-1]
    if base: return base

    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", dataset)

    return f"{safe}.log"


def main() -> int:
    ap = argparse.ArgumentParser(description="Download log datasets from LogPai LogHub.")
    ap.add_argument("--list", action="store_true", help="List available datasets and download links.")
    ap.add_argument("--dataset", type=str, default=None, help="Dataset name to download (exact match from --list).")
    ap.add_argument("--out", type=str, default=str(DEFAULT_OUT_DIR), help="Output directory (default: data/loghub).")
    ap.add_argument("--readme-url", type=str, default=LOGHUB_README_RAW, help="LogHub README raw URL.")
    args = ap.parse_args()

    print(f"Fetching LogHub index: {args.readme_url}")
    readme = http_get_text(args.readme_url)
    mapping = parse_dataset_links(readme)

    if not mapping:
        print("Could not parse datasets from README. The README format may have changed.", file=sys.stderr)
        return 2

    if args.list or not args.dataset:
        print("\nAvailable datasets (name -> download url):")
        for name in sorted(mapping.keys(), key=str.lower):
            print(f"- {name}: {mapping[name]}")
        if not args.dataset:
            print("\nTip: run with --dataset \"<name>\" to download one.")
        return 0 if args.list else 0

    dataset = args.dataset
    if dataset not in mapping:
        print(f"Dataset not found: {dataset}", file=sys.stderr)
        print("Run with --list to see exact names.", file=sys.stderr)
        return 1

    url = mapping[dataset]
    out_dir = Path(args.out) / dataset
    filename = choose_output_filename(dataset, url)
    out_path = out_dir / filename

    print(f"\nDownloading: {dataset}")
    print(f"URL: {url}")
    print(f"OUT: {out_path}")

    http_download(url, out_path)
    print("✅ Download complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())