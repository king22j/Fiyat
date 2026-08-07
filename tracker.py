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

# Steam'i normal bir tarayıcı olduğumuza ikna etmek için kimlik bilgisi (User-Agent)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

def get_inventory():
    print("Envanter çekiliyor...")
    url = f"https://steamcommunity.com/inventory/{STEAM_ID}/{APP_ID}/2?l=english&count=5000"
    
    # 429 hatası alırsak pes etmemek için 3 kere deneme döngüsü
    for attempt in range(3):
        response = requests.get(url, headers=HEADERS)
        
        if response.status_code == 429:
            print(f"Steam IP'yi kısıtladı (429). 30 saniye bekleniyor... (Deneme {attempt+1}/3)")
            time.sleep(30)
            continue # Bekledikten sonra döngünün başına dönüp tekrar dener
            
        if response.status_code != 200:
            print(f"Envanter çekilemedi. Hata kodu: {response.status_code}")
            return None

        data = response.json()
        if not data or 'assets' not in data or 'descriptions' not in data:
            print("Envanter boş veya Steam profili gizli olabilir.")
            return None

        item_descriptions = {}
        for desc in data['descriptions']:
            if desc.get('marketable', 0) == 1:
                item_descriptions[desc['classid']] = desc['market_hash_name']

        inventory_items = {}
        for asset in data['assets']:
            classid = asset['classid']
            if classid in item_descriptions:
                item_name = item_descriptions[classid]
                inventory_items[item_name] = inventory_items.get(item_name, 0) + 1

        return inventory_items
        
    return None

def get_item_price(item_name):
    url = f"https://steamcommunity.com/market/priceoverview/?appid={APP_ID}&currency={CURRENCY}&market_hash_name={item_name}"
    
    # Pazar fiyatı için 4 deneme hakkı
    for attempt in range(4):
        try:
            response = requests.get(url, headers=HEADERS)
            
            if response.status_code == 429:
                print(f"Pazardan çok fazla istek (429). 20 saniye dinleniliyor... (Deneme {attempt+1}/4)")
                time.sleep(20)
                continue
                
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and 'lowest_price' in data:
                    price_str = data['lowest_price'].replace('$', '').replace(',', '')
                    return float(price_str)
            
            # 200 başarılı aldıysa veya eşya bulunamadıysa döngüyü kır
            break 
            
        except Exception as e:
            print(f"{item_name} fiyatı çekilirken hata oluştu: {e}")
            break
            
    return 0.0

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_value": 0.0, "date": ""}

def save_history(value):
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
                "value": items_summary[:1024],
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

    print(f"Toplam {len(inventory)} farklı eşya türü bulundu. Fiyatlar çekiliyor...")
    
    total_value = 0.0
    items_summary_list = []

    for item_name, count in inventory.items():
        print(f"{item_name} (Adet: {count}) fiyatı soruluyor...")
        price = get_item_price(item_name)
        
        item_total = price * count
        total_value += item_total
        
        if item_total > 0:
            items_summary_list.append(f"• {count}x {item_name}: ${item_total:.2f} (${price:.2f}/adet)")
        
        # Her fiyat çekişinden sonra mecburi 4 saniye dinlenme
        print("Steam pazarının yorulmaması için bekleniyor (4 sn)...")
        time.sleep(4) 

    history = load_history()
    last_value = history.get("last_value", 0.0)
    
    difference = 0.0 if last_value == 0.0 else total_value - last_value

    print(f"\nHesaplama Tamamlandı. Toplam Değer: ${total_value:.2f}")

    items_summary = "\n".join(items_summary_list) if items_summary_list else "Satılabilir eşya bulunamadı."

    send_discord_webhook(total_value, difference, items_summary)
    save_history(total_value)

if __name__ == "__main__":
    main()
