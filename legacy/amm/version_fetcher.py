import urllib.request
import json
import socket
from pathlib import Path

# Tier 2: Static lookup table for non-npm runtimes
STATIC_VERSIONS = {
    "node": "22 (LTS)",
    "node.js": "22 (LTS)",
    "nodejs": "22 (LTS)",
    "python": "3.12",
    "postgresql": "17",
    "postgres": "17",
}

def fetch(stack_list: list[str]) -> dict[str, str]:
    """
    Fetch the latest versions for a list of tech stack items.
    Uses npm registry for JS packages and a static lookup for runtimes.
    """
    versions = {}
    for item in stack_list:
        clean_item = item.strip()
        lower_item = clean_item.lower()
        
        # Strip off any versions already appended by the council (e.g., "Next.js" or "Next.js 14")
        pkg_name = lower_item.split()[0].replace(".js", "")
        if lower_item.startswith("next"):
            pkg_name = "next"
            
        # 1. Tier 2: Check Static Lookup
        found_static = False
        for key, ver in STATIC_VERSIONS.items():
            if key in lower_item:
                versions[clean_item] = ver
                found_static = True
                break
        
        if found_static:
            continue
            
        # 2. Tier 1: Check NPM Registry
        npm_lookup_name = pkg_name
        # Handle specific npm names if needed
        if "tailwind" in lower_item:
            npm_lookup_name = "tailwindcss"
        elif "prisma" in lower_item:
            npm_lookup_name = "prisma"
            
        try:
            url = f"https://registry.npmjs.org/{npm_lookup_name}/latest"
            req = urllib.request.Request(url, headers={'User-Agent': 'AMM-VersionFetcher/1.0'})
            with urllib.request.urlopen(req, timeout=2.0) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    version = data.get("version")
                    if version:
                        versions[clean_item] = version
                        continue
        except (urllib.error.URLError, socket.timeout, Exception) as e:
            pass # Fall through to Tier 3
            
        # 3. Tier 3: Graceful Skip
        versions[clean_item] = "version unknown"
        print(f"  [VERSION FETCHER] Could not resolve version for: {clean_item}")
        
    return versions
