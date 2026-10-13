import sys

from playwright.sync_api import sync_playwright

URLS = sys.argv[1:] or ["https://job.nju.edu.cn/career/specifics"]

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/usr/bin/chromium",
                                args=["--no-sandbox", "--disable-dev-shm-usage"])
    for url in URLS:
        print("=" * 80)
        print("URL:", url)
        page = browser.new_page()
        api_calls = []
        page.on("request", lambda req: api_calls.append((req.method, req.url))
                if ("api" in req.url or "json" in req.url) else None)
        try:
            page.goto(url, wait_until="networkidle", timeout=45000)
        except Exception as e:
            print("goto issue:", e)
        page.wait_for_timeout(4000)
        text = page.inner_text("body")
        print("--- body text (first 1500 chars) ---")
        print(text[:1500])
        print("--- api-ish requests ---")
        seen = set()
        for m, u in api_calls:
            if u not in seen:
                seen.add(u)
                print(m, u)
        page.close()
    browser.close()
