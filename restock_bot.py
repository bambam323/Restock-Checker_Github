import os
import time
import logging
import yaml
import traceback
import requests
import urllib3
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor
from selenium.webdriver.remote.remote_connection import RemoteConnection
from selenium.webdriver.chrome.service import Service

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

# Setup Chrome WebDriver (Headless mode optional)
options = webdriver.ChromeOptions()
# options.add_argument("--headless")  # Disable this line if CAPTCHA is happening too often
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("start-maximized")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

# Automatically detect the actual User-Agent from Chrome
try:
    temp_driver = webdriver.Chrome(service=Service("/usr/local/bin/chromedriver"))
    actual_user_agent = temp_driver.execute_script("return navigator.userAgent;")
    temp_driver.quit()
    options.add_argument("user-agent=" + actual_user_agent)
    logging.info("Using detected User-Agent: " + actual_user_agent)
except Exception as e:
    logging.error("Failed to retrieve User-Agent. Defaulting to Chrome’s built-in User-Agent.")

driver = webdriver.Chrome(service=Service("/usr/local/bin/chromedriver"), options=options)
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")


def check_stock(store):
    """ Continuously checks if the product is in stock by checking if Add to Cart is enabled. """
    logging.info("Checking stock for " + store["name"] + "...")
    driver.get(store["product_url"])

    while True:
        try:
            logging.info("Checking 'Add to Cart' button...")

            # Wait for the button to appear
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
            )

            # Find the button
            add_to_cart_buttons = driver.find_elements(By.CSS_SELECTOR, store["selectors"]["add_to_cart"])

            if not add_to_cart_buttons:
                logging.warning("No 'Add to Cart' button found for " + store["name"] + ". Retrying in 2 seconds...")
            else:
                # Wait for at least one button to become enabled
                for button in add_to_cart_buttons:
                    if button.is_enabled():
                        logging.info(store["name"] + " is IN STOCK! Proceeding to checkout...")
                        add_to_cart(store)
                        return  # Stop checking once item is in stock
                
                logging.info(store["name"] + " is OUT OF STOCK. Retrying in 2 seconds...")

        except Exception as e:
            logging.error("Stock check failed for " + store["name"] + ": " + str(e))

        time.sleep(2)


def add_to_cart(store):
    """ Adds item to cart and proceeds to checkout """
    logging.info("Adding item to cart at " + store["name"] + "...")
    try:
        # Wait for the button to become clickable
        add_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
        )
        add_button.click()
        logging.info("Item added to cart at " + store["name"] + "!")
        proceed_to_checkout(store)
    except Exception as e:
        logging.error("Failed to add item to cart at " + store["name"] + ": " + str(e))


def proceed_to_checkout(store):
    """ Completes checkout process. """
    logging.info("Proceeding to checkout at " + store["name"] + "...")
    try:
        WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["view_cart"]))
        ).click()
        WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["checkout"]))
        ).click()

        WebDriverWait(driver, 1).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["payment"]["card_number"]))
        ).send_keys(CARD_NUMBER)
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["payment"]["expiry"]).send_keys(EXPIRY_DATE)
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["payment"]["cvv"]).send_keys(CVV)

        WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["payment"]["submit_button"]))
        ).click()

        logging.info("Order placed at " + store["name"] + "!")
    except Exception as e:
        logging.error("Checkout failed for " + store["name"] + ": " + str(e))


def main():
    """Runs stock checks with controlled threading."""
    logging.info("Starting Restock Bot...")
    while True:
        with ThreadPoolExecutor(max_workers=1) as executor:  # Reduce parallel checks
            executor.map(check_stock, config["websites"])
        logging.info("Sleeping for 2 seconds before checking again...")
        time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    finally:
        driver.quit()
        logging.info("Browser closed.")
