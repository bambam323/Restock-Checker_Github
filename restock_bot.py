import os
import time
import logging
import yaml
import traceback
import requests
import urllib3
import webbrowser
import random  # 🚀 Added random module for randomized delays
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor
from selenium.webdriver.remote.remote_connection import RemoteConnection

# Disable warnings & increase connection pool size
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
RemoteConnection.set_timeout(120)  # Increase timeout to prevent connection pool issues

# Load environment variables (Login & Payment Info)
load_dotenv()
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
CARD_NUMBER = os.getenv("CARD_NUMBER")
EXPIRY_DATE = os.getenv("EXPIRY_DATE")
CVV = os.getenv("CVV")
API_KEY = os.getenv("CAPTCHA_API_KEY")  # 2Captcha API key

# Mask sensitive data for logging
masked_email = EMAIL[:2] + "****@****.com"

# Load configuration file
try:
    with open("config.yaml", "r") as file:
        config = yaml.safe_load(file)
except Exception as e:
    logging.error("Failed to load config.yaml: " + str(e))
    exit(1)

# Configure logging
logging.basicConfig(filename="restock_bot.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Setup Chrome WebDriver (Fully Compatible with Older Versions)
options = webdriver.ChromeOptions()
# options.add_argument("--headless")  # Disable this line if CAPTCHA is happening too often
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("start-maximized")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

# Automatically detect the actual User-Agent from Chrome (Works with older Selenium)
try:
    temp_driver = webdriver.Chrome(executable_path="/usr/local/bin/chromedriver", options=options)
    actual_user_agent = temp_driver.execute_script("return navigator.userAgent;")
    temp_driver.quit()
    options.add_argument("user-agent=" + actual_user_agent)
    logging.info("Using detected User-Agent: " + actual_user_agent)
except Exception as e:
    logging.error("Failed to retrieve User-Agent. Defaulting to Chrome’s built-in User-Agent.")

# Start Chrome WebDriver with the correct method for older Selenium versions
driver = webdriver.Chrome(executable_path="/usr/local/bin/chromedriver", options=options)
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")


def check_price(store, retries=3):
    """Checks if the product price is within the allowed budget before purchase."""
    for attempt in range(retries):
        try:
            price_element = WebDriverWait(driver, 2).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["price"]))
            )
            price_text = price_element.text.replace("$", "").strip()
            price = float(price_text)

            if price > store["max_price"]:
                logging.warning("{} is too expensive! Price: ${}, Max Allowed: ${}".format(
                    store["name"], price, store["max_price"]
                ))
                return False  # ❌ Skip this item if it's over budget
            else:
                logging.info("{} is within budget! Price: ${}".format(store["name"], price))
                return True  # ✅ Price is good

        except Exception as e:
            logging.error("Failed to check price for {}. Attempt {}/{}. Retrying...".format(
                store["name"], attempt + 1, retries
            ))
            time.sleep(2)

    logging.error("Final price check failed for {}. Skipping item.".format(store["name"]))
    return False  # ❌ Move on if price checking fails


def check_stock(store):
    """ Continuously checks if the product is in stock and verifies price before proceeding. """
    logging.info("Checking stock for " + store["name"] + "...")

    while True:
        try:
            driver.get(store["product_url"])
            logging.info("Waiting for page to fully load...")
            time.sleep(random.uniform(2, 5))  # 🚀 Randomized delay

            logging.info("Checking 'Add to Cart' button...")

            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
            )

            add_to_cart_button = driver.find_element(By.CSS_SELECTOR, store["selectors"]["add_to_cart"])

            if add_to_cart_button.is_enabled():
                logging.info("🚀 " + store["name"] + " is IN STOCK! Verifying price...")

                if not check_price(store):  # ❌ If price is too high, skip purchase
                    logging.info("Skipping purchase due to high price.")
                    return

                logging.info("✅ Price verified! Proceeding to checkout...")
                add_to_cart_button.click()
                add_to_cart(store)
                return  # Stop checking once item is in stock

            logging.info("⏳ " + store["name"] + " is still OUT OF STOCK. Refreshing soon...")

        except Exception as e:
            logging.warning("⚠️ Button missing. Reloading page...")
            driver.get(store["product_url"])

        time.sleep(random.uniform(2, 5))  # 🚀 Randomized delay before next check


def add_to_cart(store):
    """ Adds item to cart and proceeds to checkout """
    logging.info("Adding item to cart at " + store["name"] + "...")
    try:
        add_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
        )
        add_button.click()
        logging.info("Item added to cart at " + store["name"] + "!")

        proceed_to_checkout(store)
    except Exception as e:
        logging.error("Failed to add item to cart at " + store["name"] + ": " + str(e))


def proceed_to_checkout(store):
    """Completes checkout process with automatic retry on failure."""
    logging.info("Proceeding to checkout at " + store["name"] + "...")

    attempt = 0
    max_attempts = 3  # Retry up to 3 times

    while attempt < max_attempts:
        try:
            WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["view_cart"]))
            ).click()
            logging.info("✅ Clicked 'View Cart' for " + store["name"])

            WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["checkout"]))
            ).click()
            logging.info("✅ Clicked 'Checkout' for " + store["name"])

            WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["payment"]["card_number"]))
            ).send_keys(CARD_NUMBER)
            driver.find_element(By.CSS_SELECTOR, store["selectors"]["payment"]["expiry"]).send_keys(EXPIRY_DATE)
            driver.find_element(By.CSS_SELECTOR, store["selectors"]["payment"]["cvv"]).send_keys(CVV)
            logging.info("✅ Entered payment details.")

            WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["payment"]["submit_button"]))
            ).click()
            logging.info("🎉 Order placed successfully for " + store["name"] + "!")

            return

        except Exception as e:
            attempt += 1
            logging.error("❌ Checkout failed (Attempt {}/{}): {}".format(attempt, max_attempts, str(e)))
            if attempt < max_attempts:
                logging.info("🔄 Retrying checkout soon...")
                time.sleep(random.uniform(3, 5))  # 🚀 Randomized retry delay

    logging.error("🚨 FINAL CHECKOUT FAILURE for {}. Manual intervention required.".format(store["name"]))


def main():
    logging.info("Starting Restock Bot...")
    while True:
        with ThreadPoolExecutor(max_workers=3) as executor:
            executor.map(check_stock, config["websites"])
        logging.info("Sleeping before rechecking stock...")
        time.sleep(random.uniform(2, 5))


if __name__ == "__main__":
    try:
        main()
    finally:
        driver.quit()
        logging.info("Browser closed.")
