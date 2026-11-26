import asyncio
import json
import re
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from playwright_extra import async_playwright as extra_playwright
from puppeteer_extra_plugin_stealth import stealth

GROUP_ID = "63"
URL = f"https://schedule.uksivt.ru/public?id={GROUP_ID}&mode=group&semester=1"


def parse_schedule(html):
    # ... (код парсинга из предыдущей версии без изменений) ...
    # Вставьте сюда полную функцию parse_schedule из вашего прошлого рабочего файла
    pass


async def main():
    async with extra_playwright() as p:
        # Создаем браузер с включенным stealth-плагином
        browser = await p.chromium.launch(
            headless=False, # Обязательно для обхода Turnstile, Xvfb создаст фоновый экран
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        
        # Создаем контекст с реалистичными заголовками и параметрами
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )
        
        # Применяем stealth-плагин к контексту
        await context.add_init_script(stealth())
        
        page = await context.new_page()

        print("Открываю страницу...")
        try:
            # Ждем загрузки DOM, а не полной загрузки сети
            await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            
            print("Ждем прохождения проверки Cloudflare и появления таблицы (до 45 секунд)...")
            # Увеличиваем таймаут, так как Cloudflare может проводить проверку до 45 секунд
            await page.wait_for_selector("table", timeout=45000)
            print("✅ Таблица успешно загружена!")
            
        except Exception as e:
            print(f"⚠️ Ошибка загрузки таблицы: {e}")
            with open("debug.html", "w", encoding="utf-8") as f:
                f.write(await page.content())
            await browser.close()
            raise e

        html = await page.content()
        await browser.close()

        data = parse_schedule(html)

        with open("cache.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("Успешно сохранено в cache.json!")


if __name__ == "__main__":
    asyncio.run(main())
