import asyncio

import httpx

from intent_router.main import app


def test_frontend_revalidates_html_and_module_cache():
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for path in ("/", "/route", "/static/app.js", "/static/i18n.js", "/static/route-translations.js", "/static/style.css"):
                response = await client.get(path)
                assert response.status_code == 200
                assert response.headers["cache-control"] == "no-cache"
                cached = await client.get(path, headers={"If-None-Match": response.headers["etag"]})
                assert cached.status_code in (200, 304)
                assert cached.headers["cache-control"] == "no-cache"

    asyncio.run(check())
