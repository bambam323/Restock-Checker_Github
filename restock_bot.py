import os
import time
import logging
import yaml
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Load environment variables (Login & Payment Info)
load_dotenv()
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
CARD_NUMBER = os.getenv("CARD_NUMBER")
EXPIRY_DATE = os.getenv("EXPIRY_DATE")
CVV = os.getenv("CVV")

# Load configuration file
with open("config.yaml", "r") as file:
    config = yaml.safe_load(file)

# Configure logging
logging.basicConfig(filename="restock_bot.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Setup Chrome WebDriver
options = webdriver.ChromeOptions()
options.add_argument("--headless")  # Runs in background
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def login(store):
    """ Logs into the store securely. """
    logging.info(f"Logging into {store['name']}...")
    driver.get(store["login_url"])
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["login"]["email"])))
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["login"]["email"]).send_keys(EMAIL)
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["login"]["password"]).send_keys(PASSWORD)
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["login"]["login_button"]).click()
        WebDriverWait(driver, 5).until(EC.url_changes(store["login_url"]))
        logging.info(f"✅ Login successful for {store['name']}!")
    except Exception as e:
        logging.error(f"❌ Login failed for {store['name']}: {e}")

def check_stock(store):
    """ Checks if the product is in stock for a given store. """
    logging.info(f"Checking stock for {store['name']}...")
    driver.get(store["product_url"])
    time.sleep(3)

    try:
        stock_element = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["stock"]))
        )
        stock_text = stock_element.text.lower()

        if "in stock" in stock_text:
            logging.info(f"🚀 {store['name']} item is in stock! Proceeding to checkout...")
        else:
            logging.info(f"⏳ {store['name']} is still out of stock...")

    except Exception as e:
        logging.error(f"⚠️ Stock check failed for {store['name']}: {e}")

# Run the bot for each store
try:
    for store in config["websites"]:
        login(store)
        check_stock(store)

finally:
    driver.quit()  # Close browser
    logging.info("🛑 Browser closed.")
