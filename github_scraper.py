import asyncio
import json
import re
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from playwright_stealth import Stealth  # <-- Новый импорт

GROUP_ID = "63"
URL = f"https://schedule.uksivt.ru/public?id={GROUP_ID}&mode=group&semester=1"


def parse_schedule(html):
    soup = BeautifulSoup(html, "html.parser")
    days_data = {}

    tables = soup.find_all("table")
    if not tables:
        raise RuntimeError("Таблица не найдена. Возможно, защита не пройдена.")

    table = tables[0]
    rows = table.find_all("tr")

    headers = []
    for th in rows[0].find_all(["th", "td"]):
        text = th.get_text(" ", strip=True)
        m = re.search(
            r'(Понедельник|Вторник|Среда|Четверг|Пятница|Суббота|Воскресенье),?\s*(\d{1,2}\.\d{1,2})',
            text, re.I
        )
        if m:
            day_name = f"{m.group(1)} {m.group(2)}"
            headers.append(day_name)
            days_data[day_name] = []
        else:
            headers.append(None)

    for tr in rows[1:]:
        cells = tr.find_all(["td", "th"])
        if len(cells) < 2:
            continue

        first_cell_text = cells[0].get_text(" ", strip=True)
        pm = re.match(r'^(\d+)\s*(\d{2}:\d{2})(?:\s*(\d{2}:\d{2}))?', first_cell_text)
        if not pm:
            continue

        para = pm.group(1)
        t1 = pm.group(2)
        t2 = pm.group(3)
        default_time = f"{t1}-{t2}" if t2 else t1

        for idx, cell in enumerate(cells[1:]):
            day_idx = idx + 1
            if day_idx >= len(headers):
                break
            day_name = headers[day_idx]
            if not day_name:
                continue

            cell_text = cell.get_text("\n", strip=True)
            if not cell_text or cell_text in ["—", "-"]:
                continue

            lines = [l.strip() for l in cell_text.split("\n") if l.strip()]
            if not lines:
                continue

            subject, replace, room, actual_time = "", "", "", default_time

            room_m = re.search(r'каб\.\s*([\w\-/]+)', cell_text)
            if room_m:
                room = room_m.group(1)

            if "замена" in cell_text.lower():
                rep_match = re.search(r'замена\s+(.+)', cell_text, re.I | re.S)
                if rep_match:
                    replace = rep_match.group(1).replace("\n", " ").strip()

                orig_idx = cell_text.lower().find("замена")
                original_part = cell_text[:orig_idx].strip()
                orig_lines = [l.strip() for l in original_part.split("\n") if l.strip()]
                for line in orig_lines:
                    if re.match(r'^\d{1,2}:\d{2}\s*[-–—]\s*\d{1,2}:\d{2}$', line):
                        continue
                    cleaned = re.sub(r'^(нечёт|чёт)[\s:]*', '', line, flags=re.I).strip()
                    if cleaned and not cleaned.startswith("каб") and len(cleaned) > 2:
                        subject = cleaned
                        break
                if not subject and replace:
                    subject = replace.split("→")[0].split("—")[0].strip()
            else:
                for line in lines:
                    time_m = re.match(r'^(\d{1,2}:\d{2})\s*[-–—]\s*(\d{1,2}:\d{2})$', line)
                    if time_m:
                        actual_time = f"{time_m.group(1)}-{time_m.group(2)}"
                        continue
                    cleaned = re.sub(r'^(нечёт|чёт)[\s:]*', '', line, flags=re.I).strip()
                    if cleaned and not cleaned.startswith("каб") and len(cleaned) > 2:
                        if not subject:
                            subject = cleaned

            if subject == actual_time:
                subject = ""

            if subject or replace:
                days_data[day_name].append({
                    "para": para,
                    "time": actual_time,
                    "subject": subject,
                    "room": room,
                    "replace": replace
                })

    return {"days": days_data, "group": "25ВЕБ-3"}


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 1. Применяем маскировку для обхода защиты от ботов
        await Stealth().apply_stealth_async(page) 
        
        # 2. Устанавливаем реалистичный User-Agent
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

        print("Открываю страницу...")
        # 3. Используем networkidle, чтобы дождаться всех запросов сайта
        await page.goto(URL, wait_until="networkidle", timeout=60000)

        print("Ждем загрузки таблицы (до 30 секунд)...")
        try:
            # 4. Увеличиваем таймаут ожидания таблицы
            await page.wait_for_selector("table", timeout=30000) 
            print("Таблица успешно загружена!")
        except Exception as e:
            print(f"⚠️ Таблица не появилась: {e}")
            # Сохраняем HTML для отладки, если таблица так и не появилась
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
