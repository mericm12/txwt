import asyncio
from playwright.async_api import async_playwright
import xml.etree.ElementTree as ET
from datetime import datetime
import os
import re
import requests
import subprocess

TARGET_USER = "Haber"
MAX_TWEETS = 3  # Kaç tweet işlenecek

def sanitize_filename(text):
    return re.sub(r'[^a-zA-Z0-9-_]', '_', text)[:50]

def download_file(url, save_path):
    try:
        r = requests.get(url, stream=True)
        if r.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
    except Exception as e:
        print("Görsel indirme hatası:", e)

def download_twitter_video(tweet_url, save_path):
    try:
        subprocess.run([
            'yt-dlp',
            tweet_url,
            '-f', 'mp4',
            '-o', save_path
        ], check=True)
    except Exception as e:
        print("🎥 Video indirme hatası (yt-dlp):", e)

async def fetch_tweets():
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(f"https://twitter.com/{TARGET_USER}", timeout=60000)
        await page.wait_for_timeout(5000)

        articles = await page.query_selector_all('article')
        count = 0

        for article in articles:
            if count >= MAX_TWEETS:
                break

            try:
                text_el = await article.query_selector('div[lang]')
                time_el = await article.query_selector('time')
                if not text_el or not time_el:
                    continue

                tweet_text = await text_el.inner_text()
                tweet_url = await time_el.evaluate("node => node.parentElement.href")
                full_url = f"{tweet_url}"

                # Tweet sayfasına git
                tweet_page = await context.new_page()
                await tweet_page.goto(full_url)
                await tweet_page.wait_for_selector('time')
                time_tag = await tweet_page.query_selector('time')
                tweet_time = await time_tag.get_attribute("datetime")
                dt = datetime.strptime(tweet_time, "%Y-%m-%dT%H:%M:%S.%fZ")

                # Görsel kontrolü
                image_el = await tweet_page.query_selector('img[src*="pbs.twimg.com/media"]')
                image_url = await image_el.get_attribute("src") if image_el else ""

                results.append({
                    "text": tweet_text,
                    "url": full_url,
                    "time": dt,
                    "image": image_url
                })

                await tweet_page.close()
                count += 1

            except Exception as e:
                print("Tweet hatası:", e)
                continue

        await browser.close()
    return results

def save_tweet_folder(tweet):
    # Ay klasörü (örnek: 2025-05)
    month_folder = tweet["time"].strftime("%Y-%m")
    os.makedirs(month_folder, exist_ok=True)

    # Gün klasörü (örnek: 2025-05-26)
    date_folder = tweet["time"].strftime("%Y-%m-%d")
    full_date_path = os.path.join(month_folder, date_folder)
    os.makedirs(full_date_path, exist_ok=True)

    # Tweet alt klasörü (örnek: Dries_Mertens_2025-05-26)
    first_words = ' '.join(tweet["text"].split()[:2])
    tweet_folder_name = sanitize_filename(f"{first_words}_{date_folder}")
    tweet_path = os.path.join(full_date_path, tweet_folder_name)
    os.makedirs(tweet_path, exist_ok=True)

    # Görsel veya video indir
    if tweet["image"]:
        img_path = os.path.join(tweet_path, "image.jpg")
        download_file(tweet["image"], img_path)
    else:
        video_path = os.path.join(tweet_path, "video.mp4")
        download_twitter_video(tweet["url"], video_path)

    # XML oluştur
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = first_words
    ET.SubElement(channel, "link").text = tweet["url"]
    ET.SubElement(channel, "description").text = tweet["text"]

    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = tweet["text"]
    ET.SubElement(item, "link").text = tweet["url"]
    ET.SubElement(item, "pubDate").text = tweet["time"].strftime("%a, %d %b %Y %H:%M:%S +0000")

    desc = f"<p>{tweet['text']}</p>"
    if tweet["image"]:
        desc += f'<br><img src="image.jpg" style="max-width:100%"/>'
    else:
        desc += f'<br><video controls src="video.mp4" style="max-width:100%"></video>'

    ET.SubElement(item, "description").text = desc
    tree = ET.ElementTree(rss)
    tree.write(os.path.join(tweet_path, "tweet.xml"), encoding="utf-8", xml_declaration=True)

    print(f"📁 Klasör oluşturuldu: {tweet_path}")

async def main():
    print("🔄 Tweetler çekiliyor...")
    tweets = await fetch_tweets()
    for tweet in tweets:
        save_tweet_folder(tweet)
    print("✅ Tüm klasörler ve içerikler hazır.")

if __name__ == "__main__":
    asyncio.run(main())
