import os
import time
import logging
import yaml
import traceback
import requests
import urllib3
import webbrowser
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor
from selenium.webdriver.remote.remote_connection import RemoteConnection
import threading  # Older threading method

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

# Runs all stock checks in separate threads
def check_stock(store):
    """Runs stock checks in a separate WebDriver instance per product (compatible with older Python & Selenium)."""
    logging.info("Checking stock for " + store["name"] + "...")

    # 🚀 Start a new WebDriver instance for each product
    stock_driver = webdriver.Chrome(executable_path="/usr/local/bin/chromedriver", options=options)

    while True:
        try:
            stock_driver.get(store["product_url"])
            logging.info("Waiting for page to fully load... (" + store["name"] + ")")
            time.sleep(3)  # Ensure JavaScript elements load

            logging.info("Checking 'Add to Cart' button... (" + store["name"] + ")")
            add_to_cart_button = WebDriverWait(stock_driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
            )

            if add_to_cart_button.is_enabled():
                logging.info("🚀 " + store["name"] + " is IN STOCK! Verifying price...")

                if check_price(store, stock_driver):  # Ensure price is within budget
                    logging.info("✅ Price verified! Proceeding to checkout... (" + store["name"] + ")")

                    # Run checkout in a separate thread (older method)
                    checkout_thread = threading.Thread(target=add_to_cart, args=(store, stock_driver))
                    checkout_thread.start()

                    return  # Exit loop once an item is being checked out

                else:
                    logging.info("⏳ " + store["name"] + " is too expensive. Waiting for price drop.")

            else:
                logging.info("⏳ " + store["name"] + " is still OUT OF STOCK. Refreshing soon...")

        except Exception as e:
            logging.error("Stock check failed for " + store["name"] + ": " + str(e))
            logging.error("Full Exception Traceback:\n" + traceback.format_exc())

        time.sleep(3)  # Prevent excessive requests

# Checks price before purchasing
def check_price(store, driver):
    """Checks if the product price is within the allowed budget before purchase."""
    try:
        price_element = WebDriverWait(driver, 1).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["price"]))
        )
        price_text = price_element.text.replace("$", "").strip()
        price = float(price_text)

        if price > store["max_price"]:
            logging.warning(store["name"] + " is too expensive! Price: $" + str(price) + ", Max Allowed: $" + str(store["max_price"]))
            return False
        else:
            logging.info(store["name"] + " is within budget! Price: $" + str(price))
            return True  # ✅ Now the function correctly returns True if price is OK
    except Exception as e:
        logging.error("Failed to check price for " + store["name"] + ". Skipping.")
        return False  # Move on after failure

# Adds the product to cart and interacts with the "Added to Cart" modal
def add_to_cart(store, driver):
    """ Adds item to cart and interacts with the 'Added to Cart' modal before proceeding to checkout """
    logging.info("Adding item to cart at " + store["name"] + "...")

    try:
        # Wait for the "Add to Cart" button to become clickable
        add_button = WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
        )

        add_button.click()
        logging.info("✅ Item added to cart at " + store["name"] + "! Waiting for confirmation...")

        # Wait for "Added to Cart" modal to appear
        modal = WebDriverWait(driver, 2).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-test='content-wrapper']"))
        )
        logging.info("🛒 'Added to Cart' modal detected!")

        # Click "View Cart & Check Out" inside the modal
        checkout_button = WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.LINK_TEXT, "View cart & check out"))
        )
        checkout_button.click()
        logging.info("✅ Navigated to cart page. Proceeding to checkout...")

        proceed_to_checkout(store, driver)

    except Exception as e:
        logging.error("❌ Failed to add item to cart at " + store["name"] + ": " + str(e))

# Completes checkout process
def proceed_to_checkout(store, driver):
    """Completes checkout process."""
    logging.info("Proceeding to checkout at " + store["name"] + "...")

    try:
        WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["checkout"]))
        ).click()

        WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["payment"]["card_number"]))
        ).send_keys(CARD_NUMBER)
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["payment"]["expiry"]).send_keys(EXPIRY_DATE)
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["payment"]["cvv"]).send_keys(CVV)

        WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["payment"]["submit_button"]))
        ).click()

        logging.info("🎉 Order placed successfully for " + store["name"] + "!")
    except Exception as e:
        logging.error("❌ Checkout failed for " + store["name"] + ": " + str(e))

# Runs stock checks for all products at the same time
def main():
    """Runs stock checks for all products simultaneously."""
    logging.info("Starting Restock Bot...")
    threads = []
    for store in config["websites"]:
        t = threading.Thread(target=check_stock, args=(store,))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

if __name__ == "__main__":
    try:
        main()
    finally:
        logging.info("Browser closed.")
