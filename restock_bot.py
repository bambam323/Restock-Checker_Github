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


def check_stock(store):
    """ Continuously checks if the product is in stock while reducing detection risks. """
    logging.info("Checking stock for " + store["name"] + "...")

    while True:
        try:
            driver.get(store["product_url"])
            logging.info("Waiting for page to fully load...")
            time.sleep(random.uniform(2, 5))  # 🚀 Randomized delay to prevent detection

            logging.info("Checking 'Add to Cart' button...")

            # Reduced timeout from 15s to 5s for faster failures
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
            )

            logging.info("Successfully obtained WebDriver")

            # Find all buttons matching the selector
            add_to_cart_buttons = driver.find_elements(By.CSS_SELECTOR, store["selectors"]["add_to_cart"])

            if not add_to_cart_buttons:
                logging.warning("No 'Add to Cart' button found for " + store["name"] + ". Retrying soon...")

                # 🚀 Automatically save and open the screenshot
                screenshot_path = os.path.join(os.getcwd(), "debug_screenshot.png")
                driver.save_screenshot(screenshot_path)
                logging.warning("Screenshot saved at: " + screenshot_path)

                # 🚀 Auto-open the screenshot
                webbrowser.open(screenshot_path)

            else:
                for button in add_to_cart_buttons:
                    if button.is_enabled():
                        logging.info(store["name"] + " is IN STOCK! Proceeding to checkout...")
                        button.click()
                        add_to_cart(store)
                        return  # Stop checking once item is in stock
                
                logging.info(store["name"] + " is OUT OF STOCK. Retrying soon...")

        except Exception as e:
            logging.error("Stock check failed for " + store["name"] + ": " + str(e))
            logging.error("Full Exception Traceback:\n" + traceback.format_exc())

        time.sleep(random.uniform(2, 4))  # 🚀 Randomized delay before retrying


def add_to_cart(store):
    """ Adds item to cart and proceeds to checkout """
    logging.info("Adding item to cart at " + store["name"] + "...")
    try:
        # Reduced timeout for faster response
        add_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
        )
        add_button.click()
        logging.info("Item added to cart at " + store["name"] + "!")
        proceed_to_checkout(store)
    except Exception as e:
        logging.error("Failed to add item to cart at " + store["name"] + ": " + str(e))


def proceed_to_checkout(store):
    """Completes checkout process with automatic retry on failure (Optimized for Older Selenium)"""
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
            logging.info("✅ Entered payment details for " + store["name"])

            WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["payment"]["submit_button"]))
            ).click()
            logging.info("🎉 Order placed successfully for " + store["name"] + "!")

            return  # Exit loop if checkout is successful

        except Exception as e:
            attempt += 1
            logging.error("❌ Checkout failed (Attempt {}/{}): {}".format(attempt, max_attempts, str(e)))
            if attempt < max_attempts:
                logging.info("🔄 Retrying checkout soon...")
                time.sleep(random.uniform(3, 5))  # 🚀 Randomized retry delay

    logging.error("🚨 FINAL CHECKOUT FAILURE for {}. Manual intervention required.".format(store["name"]))


def main():
    """Runs stock checks continuously with controlled delays."""
    logging.info("Starting Restock Bot...")
    while True:
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.map(check_stock, config["websites"])
        logging.info("Sleeping before rechecking stock...")
        time.sleep(random.uniform(2, 5))  # 🚀 Randomized interval before looping


if __name__ == "__main__":
    try:
        main()
    finally:
        driver.quit()
        logging.info("Browser closed.")
