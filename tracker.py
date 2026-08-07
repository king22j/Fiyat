import requests
import time
import json
import os
from datetime import datetime

# GitHub Secrets'tan alınacak bilgiler
STEAM_ID = os.environ.get("STEAM_ID")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

HISTORY_FILE = "history.json"
APP_ID = "730" # CS2 oyun kodu
CURRENCY = "1" # 1 = USD (Dolar)

def get_inventory():
    print("Envanter çekiliyor...")
    # Sadece SteamID'ne ait CS2 envanterini çeker
    url = f"https://steamcommunity.com/inventory/{STEAM_ID}/{APP_ID}/2?l=english&count=5000"
    response = requests.get(url)
    
    if response.status_code != 200:
        print(f"Envanter çekilemedi. Hata kodu: {response.status_code}")
        return None

    data = response.json()
    if not data or 'assets' not in data or 'descriptions' not in data:
        print("Envanter boş veya Steam profili gizli olabilir.")
        return None

    # Eşya detaylarını (isimlerini) bir sözlükte eşleştirelim
    item_descriptions = {}
    for desc in data['descriptions']:
        if desc.get('marketable', 0) == 1: # Sadece pazarda satılabilir eşyalar
            item_descriptions[desc['classid']] = desc['market_hash_name']

    # Aynı eşyadan kaç tane olduğunu sayalım (Örn: 50 tane Prisma 2 Kasası)
    inventory_items = {}
    for asset in data['assets']:
        classid = asset['classid']
        if classid in item_descriptions:
            item_name = item_descriptions[classid]
            inventory_items[item_name] = inventory_items.get(item_name, 0) + 1

    return inventory_items

def get_item_price(item_name):
    # Doğrudan Steam Topluluk Pazarı'ndan eşya fiyatını çeker
    url = f"https://steamcommunity.com/market/priceoverview/?appid={APP_ID}&currency={CURRENCY}&market_hash_name={item_name}"
    
    try:
        response = requests.get(url)
        if response.status_code == 429:
            print("Çok fazla istek atıldı (Rate Limit). 15 saniye dinleniliyor...")
            time.sleep(15)
            response = requests.get(url)
            
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and 'lowest_price' in data:
                # Steam fiyatı string olarak yollar (Örn: "$5.43"), bunu sayısal değere çeviriyoruz
                price_str = data['lowest_price'].replace('$', '').replace(',', '')
                return float(price_str)
    except Exception as e:
        print(f"{item_name} fiyatı çekilirken hata oluştu: {e}")
        
    return 0.0

def load_history():
    # Dünkü fiyatı json dosyasından okur
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_value": 0.0, "date": ""}

def save_history(value):
    # Bugünkü güncel değeri yarına referans olması için json dosyasına yazar
    data = {
        "last_value": value,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)

def send_discord_webhook(total_value, difference, items_summary):
    if not WEBHOOK_URL:
        print("Webhook URL bulunamadı, Discord'a mesaj gönderilmedi.")
        return

    # Artış varsa yeşil, azalış varsa kırmızı renk kodunu belirler
    color = 3066993 if difference >= 0 else 15158332 
    symbol = "+" if difference >= 0 else ""

    embed = {
        "title": "📊 Günlük Steam Envanter Raporu",
        "color": color,
        "fields": [
            {
                "name": "💰 Toplam Değer",
                "value": f"**${total_value:.2f}**",
                "inline": True
            },
            {
                "name": "📈 Düne Göre Değişim",
                "value": f"**{symbol}${difference:.2f}**",
                "inline": True
            },
            {
                "name": "📦 Envanter Özeti (Değerli Eşyalar)",
                "value": items_summary[:1024], # Discord mesaj sınırı için ilk 1024 karakter
                "inline": False
            }
        ]
    }

    payload = {"embeds": [embed]}
    requests.post(WEBHOOK_URL, json=payload)

def main():
    inventory = get_inventory()
    if not inventory:
        return

    print(f"Toplam {len(inventory)} farklı eşya türü bulundu. Fiyatlar Steam pazarından çekiliyor...")
    
    total_value = 0.0
    items_summary_list = []

    # Envanterdeki tüm eşyaları döngüye sokup fiyatlarını tek tek çekiyoruz
    for item_name, count in inventory.items():
        print(f"{item_name} (Adet: {count}) fiyatı soruluyor...")
        price = get_item_price(item_name)
        
        item_total = price * count
        total_value += item_total
        
        if item_total > 0:
            items_summary_list.append(f"• {count}x {item_name}: ${item_total:.2f} (${price:.2f}/adet)")
        
        # STEAM BAN YEMEMEK İÇİN DİNLENME SÜRESİ (4 Saniye)
        print("Steam pazarının yorulmaması için bekleniyor (4 sn)...")
        time.sleep(4) 

    # Geçmiş veriyi oku ve artış/azalışı hesapla
    history = load_history()
    last_value = history.get("last_value", 0.0)
    
    # Eğer program ilk defa çalışıyorsa değişimi 0 kabul et
    if last_value == 0.0:
        difference = 0.0
    else:
        difference = total_value - last_value

    print(f"\nHesaplama Tamamlandı. Toplam Değer: ${total_value:.2f}")

    items_summary = "\n".join(items_summary_list) if items_summary_list else "Satılabilir eşya bulunamadı."

    # Raporu gönder ve veriyi kaydet
    send_discord_webhook(total_value, difference, items_summary)
    save_history(total_value)

if __name__ == "__main__":
    main()
