import os
import time
import logging
import yaml
import requests
import traceback
from threading import Thread
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
options.add_argument("--headless")  # Runs Chrome without UI
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")  # Anti-bot detection bypass
options.add_argument("start-maximized")  # Ensures website loads properly
options.add_experimental_option("excludeSwitches", ["enable-automation"])  # Hides automation flag
options.add_experimental_option("useAutomationExtension", False)  # Disables automation extension

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")  # Hides Selenium usage

def login(store):
    """ Logs into the store securely. """
    logging.info("Logging into " + store["name"] + "...")
    driver.get(store["login_url"])
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["login"]["email"])))
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["login"]["email"]).send_keys(EMAIL)
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["login"]["password"]).send_keys(PASSWORD)
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["login"]["login_button"]).click()
        WebDriverWait(driver, 5).until(EC.url_changes(store["login_url"]))
        logging.info("✅ Login successful for " + store["name"] + "!")
    except Exception as e:
        logging.error("❌ Login failed for " + store["name"] + ": " + str(e))

def check_stock(store):
    """ Checks if the product is in stock for a given store. """
    logging.info("Checking stock for " + store["name"] + "...")
    driver.get(store["product_url"])

    retries = 3

    for attempt in range(retries):
        try:
            stock_element = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["stock"]))
            )
            stock_text = stock_element.text.lower()

            if "in stock" in stock_text:
                logging.info("🚀 " + store["name"] + " item is in stock! Proceeding to checkout...")
                add_to_cart(store)
                return
            else:
                logging.info("⏳ " + store["name"] + " is still out of stock...")

        except Exception as e:
            logging.error("⚠️ Stock check failed for " + store["name"] + " on attempt " + str(attempt + 1) + ": " + traceback.format_exc())

    logging.error("❌ Giving up on " + store["name"] + " after " + str(retries) + " failed attempts.")

def add_to_cart(store):
    """ Adds item to cart and proceeds to checkout """
    logging.info("🛒 Adding item to cart at " + store["name"] + "...")
    
    try:
        add_button = WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
        )
        add_button.click()
        logging.info("✅ Item added to cart at " + store["name"] + "!")

        proceed_to_checkout(store)
    except Exception as e:
        logging.error("❌ Failed to add item to cart at " + store["name"] + ": " + str(e))

def proceed_to_checkout(store):
    """ Completes checkout process including payment """
    logging.info("💳 Proceeding to checkout at " + store["name"] + "...")
    driver.get(store["checkout_url"])

    try:
        WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["checkout"]))
        ).click()

        # Handling CAPTCHA
        if store["selectors"].get("captcha"):
            bypass_captcha(store)

        # Enter Payment Details
        WebDriverWait(driver, 2).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["payment"]["card_number"]))
        ).send_keys(CARD_NUMBER)

        driver.find_element(By.CSS_SELECTOR, store["selectors"]["payment"]["expiry"]).send_keys(EXPIRY_DATE)
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["payment"]["cvv"]).send_keys(CVV)

        # Submit Order
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["payment"]["submit_button"]).click()
        logging.info("🎉 Order placed at " + store["name"] + "!")
    except Exception as e:
        logging.error("❌ Checkout failed for " + store["name"] + ": " + str(e))

driver.quit()
logging.info("🛑 Browser closed.")


finally:
    driver.quit()  # Close browser
    logging.info("🛑 Browser closed.")
