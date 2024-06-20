import requests
from bs4 import BeautifulSoup
import json
import os
import time
import gc
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import html

# Browser settings
chrome_options = Options()
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--headless')

# Adding logging parameters to intercept network requests
capabilities = chrome_options.to_capabilities()
capabilities['goog:loggingPrefs'] = {'performance': 'ALL'}

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
driver.execute_cdp_cmd('Network.enable', {})

# Main page URL
url = 'https://mytuner-radio.com/'
headers = {
    "Accept": "*/*",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36"
}
req = requests.get(url, headers=headers)
src = req.text

soup = BeautifulSoup(src, 'lxml')

# Extract all continents
continents = soup.find(class_='continents').find_all(class_='tablinks')

# Create directories for storing data
os.makedirs('data', exist_ok=True)
os.makedirs('json_data', exist_ok=True)
os.makedirs('data_res', exist_ok=True)

product_info = []
path = 0

# Iterate through each continent
for continent in continents:
    continent_name = continent.text.strip()
    continent_button_id = continent['id']
    print("Continent:", continent_name)
    print("Button ID:", continent_button_id)

    # Extract list of countries
    country_links = soup.find(id=f'{continent_name}').find_all('a')

    for country in country_links:
        country_href = 'https://mytuner-radio.com' + country.get('href')
        country_name = html.unescape(country.text.strip())  # Decode HTML entities

        all_categories_dict = {}
        page_number = 1

        while True:
            # Form the URL for the current page
            current_page_url = country_href + f'?page={page_number}' if page_number > 1 else country_href
            req = requests.get(current_page_url, headers=headers)
            src = req.text
            soup = BeautifulSoup(src, 'lxml')

            # Extract list of cities
            all_products_hrefs = soup.find_all(class_='no-select')

            for item in all_products_hrefs:
                item_text_list = item.find_all(class_='ellipsize')
                for item_text in item_text_list:
                    item_name = html.unescape(item_text.text)  # Decode HTML entities
                    item_href = item.get('href')
                    if item_href is not None:
                        item_href = 'https://mytuner-radio.com' + item_href
                        all_categories_dict[item_name] = item_href

            # Check for the next page button
            next_page_button = soup.find('a', class_='number', href=True, string=str(page_number + 1))
            if next_page_button:
                page_number += 1
            else:
                break

        os.makedirs(f'{continent_name}', exist_ok=True)

        # Uncomment the following line if you need to save the dictionary again
        with open(f'{continent_name}/{continent_name}_{country_name}_dict.json', 'w', encoding="utf-8") as file:
            json.dump(all_categories_dict, file, indent=4, ensure_ascii=False)
        file_path = f'{continent_name}/{continent_name}_{country_name}_dict.json'
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}. Skipping {country_name}.")
            continue
        with open(f'{continent_name}/{continent_name}_{country_name}_dict.json', 'r', encoding="utf-8") as file:
            all_categories = json.load(file)

        count = 0
        for categories_name, categories_href in all_categories.items():
            print(f'Processing count: {count}, categories_name: {categories_name}')  # For checking
            try:
                rep = [',', ' ', '-', '\'','/','|','+','___','____','_____',':','*','?','.','<','>']
                for item in rep:
                    if item in categories_name:
                        categories_name = categories_name.replace(item, '_')

                req = requests.get(url=categories_href, headers=headers)
                src = req.text
                with open(f'data/{count}_{categories_name}.html', 'w', encoding="utf-8") as file:
                    file.write(src)
                with open(f'data/{count}_{categories_name}.html', 'r', encoding="utf-8") as file:
                    src = file.read()

                soup = BeautifulSoup(src, 'lxml')

                # Search for embedded JSON data
                script_tags = soup.find_all('script', type='application/ld+json')
                radio_station_data = None
                for script in script_tags:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, list):
                            for item in data:
                                if item.get('@type') == 'RadioStation':
                                    radio_station_data = item
                                    break
                        elif data.get('@type') == 'RadioStation':
                            radio_station_data = data
                    except json.JSONDecodeError:
                        continue
                    if radio_station_data:
                        break

                if not radio_station_data:
                    continue

                # Save JSON data from the page
                with open(f'json_data/{count}_{categories_name}.json', 'w', encoding="utf-8") as file:
                    json.dump(radio_station_data, file, indent=4, ensure_ascii=False)

                # Extract data from JSON
                name = html.unescape(radio_station_data.get('name', 'Unknown'))  # Decode HTML entities
                image = radio_station_data.get('image', {}).get('url', 'Unknown')

                # Extract location data
                country_name = soup.find(class_='main-content').find_all('a')
                country = country_name[0].text.strip() if len(country_name) > 0 else 'Unknown'
                state = country_name[1].text.strip() if len(country_name) > 1 else 'Unknown'
                city = country_name[2].text.strip() if len(country_name) > 2 else 'Unknown'

                # Check for 'contacts' element
                contacts_section = soup.find(class_='contacts')
                if contacts_section:
                    homepage_element = contacts_section.find('a')
                    if homepage_element:
                        homepage = homepage_element.text
                        if not homepage.startswith('https://'):
                            homepage = 'https://' + homepage
                    else:
                        homepage = 'Unknown'
                else:
                    homepage = 'Unknown'

                # Extract genres
                genre_tags = soup.find(class_='radio-player').find(class_='genres').find_all('a')
                genres = ', '.join([genre.text for genre in genre_tags]) if genre_tags else 'Unknown'

                # Intercept network requests to get the audio stream
                driver.get(categories_href)
                initial_windows = driver.window_handles

                # Find and click the play button
                try:
                    play_button = driver.find_element(By.ID, 'play-button')
                    play_button.click()
                    time.sleep(5)
                    new_windows = driver.window_handles
                    if len(new_windows) > len(initial_windows):
                        new_window = new_windows[-1]
                        driver.switch_to.window(new_window)
                        time.sleep(5)  # Add a delay to allow the new window to load
                        try:
                            play_button_new_window = driver.find_element(By.ID, 'play-button')
                            play_button_new_window.click()
                        except Exception as e:
                            print(f"Error clicking play button in new window: {e}")

                    logs = driver.get_log('performance')
                    url_resolved = None
                    for entry in logs:
                        log = json.loads(entry['message'])
                        message = log['message']
                        if 'Network.responseReceived' in message['method'] and 'response' in message['params']:
                            response = message['params']['response']
                            url = response['url']
                            mimeType = response.get('mimeType', '')
                            if 'audio' in mimeType or any(
                                    ext in url for ext in ['.mp3', '.aac', '.m3u8', '.ogg', '.aacp']):
                                url_resolved = url
                                break
                except Exception as e:
                    print(f"Error intercepting audio stream: {e}")
                    url_resolved = None

                product_info.append({
                    'name': name,
                    'url': categories_href,
                    'url_resolved': url_resolved if url_resolved else "Unknown",
                    'homepage': homepage,
                    'image': image,
                    'country': country,
                    'state': state,
                    'city': city,
                    'genres': genres,
                })

                count += 1
                gc.collect()

            except Exception as e:
                print(f"Error processing {categories_name}: {e}")
                continue

            with open(f'data_res/{continent_name}_info.json', 'w', encoding="utf-8") as file:
                json.dump(product_info, file, indent=4, ensure_ascii=False)

    driver.quit()
