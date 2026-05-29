"""Probe whether a SN KB article body renders anonymously via a headless browser."""
import asyncio
import contextlib

from playwright.async_api import async_playwright

URL = "https://sydneyuni.service-now.com/sm?id=kb_article_view&sys_kb_id=b6022d07c36b79500b2b329f05013174"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        resp = await page.goto(URL, wait_until="networkidle", timeout=45000)
        print("status:", resp.status if resp else "?")
        print("url:", page.url)
        # Wait briefly for any lazy renders
        with contextlib.suppress(Exception):
            await page.wait_for_selector("[ng-bind-html], .kb-article, article, .sp-rich-text", timeout=5000)
        html = await page.content()
        print("len:", len(html))
        for needle in ("EndNote", "endnote", "Sign in", "UniKey", "Okta"):
            print(f"has {needle!r}:", needle in html)
        # try to get just the article body text
        body_text = await page.evaluate(
            """() => {
                const sel = [
                    '[ng-bind-html]',
                    '.kb-article-content',
                    '.kb-article',
                    'article',
                    '.sp-rich-text'
                ];
                for (const s of sel) {
                    const el = document.querySelector(s);
                    if (el && el.innerText && el.innerText.length > 100) {
                        return {selector: s, text: el.innerText.slice(0, 4000)};
                    }
                }
                return {selector: null, text: document.body ? document.body.innerText.slice(0, 4000) : ''};
            }"""
        )
        print("\nselector matched:", body_text.get("selector"))
        print("\n--- body text (first 2000 chars) ---")
        print((body_text.get("text") or "")[:2000])
        await browser.close()

asyncio.run(main())
