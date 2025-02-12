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

# Disable warnings & increase connection pool size
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
RemoteConnection.set_timeout(30)  # Increase timeout to prevent connection issues

# Load environment variables (Login & Payment Info)
load_dotenv()
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
CARD_NUMBER = os.getenv("CARD_NUMBER")
EXPIRY_DATE = os.getenv("EXPIRY_DATE")
CVV = os.getenv("CVV")
API_KEY = "your_2captcha_api_key"  # Replace with your 2Captcha API key if using reCAPTCHA

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

# Setup Chrome WebDriver
options = webdriver.ChromeOptions()
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("start-maximized")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

driver = webdriver.Chrome(executable_path="/usr/local/bin/chromedriver", options=options)
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")


def check_for_captcha():
    """Detects and solves CAPTCHA if present using 2Captcha."""
    try:
        captcha_iframe = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='captcha']")
        if captcha_iframe:
            logging.warning("CAPTCHA detected! Attempting to solve automatically...")
            site_key = "your_target_site_key_here"  # Extract from HTML source
            page_url = driver.current_url

            # Request CAPTCHA solution from 2Captcha
            captcha_id = requests.post(
                f"http://2captcha.com/in.php?key={API_KEY}&method=userrecaptcha&googlekey={site_key}&pageurl={page_url}&json=1"
            ).json().get("request")

            logging.info("Waiting for CAPTCHA solution...")
            time.sleep(15)  # Allow time for CAPTCHA workers to solve it

            # Retrieve solution
            captcha_solution = requests.get(
                f"http://2captcha.com/res.php?key={API_KEY}&action=get&id={captcha_id}&json=1"
            ).json().get("request")

            if captcha_solution:
                logging.info("CAPTCHA solved successfully!")
                driver.execute_script(
                    f"document.getElementById('g-recaptcha-response').innerHTML = '{captcha_solution}';"
                )
                return True
            else:
                logging.error("Failed to solve CAPTCHA.")
                return False
    except Exception as e:
        logging.error("Error solving CAPTCHA: {}".format(str(e)))


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
                return False
            else:
                logging.info("{} is within budget! Price: ${}".format(store["name"], price))
                return True
        except Exception as e:
            logging.error("Failed to check price for {}. Attempt {}/{}. Retrying in 2 seconds...".format(
                store["name"], attempt + 1, retries
            ))
            time.sleep(2)

    logging.error("Final price check failed for {} after {} attempts. Skipping this item.".format(store["name"], retries))
    return False


def check_stock(store):
    """ Continuously checks if the product is in stock. """
    logging.info("Checking stock for {}...".format(store["name"]))
    driver.get(store["product_url"])
    
    while True:
        try:
            check_for_captcha()

            if not check_price(store):
                return

            logging.info("Checking 'Add to Cart' button...")
            add_to_cart_button = WebDriverWait(driver, 2).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
            )
            if not add_to_cart_button.get_attribute("disabled"):
                logging.info("{} is IN STOCK! Proceeding to checkout...".format(store["name"]))
                add_to_cart(store)
                return
            else:
                logging.info("{} is OUT OF STOCK.".format(store["name"]))
        except Exception as e:
            logging.error("Stock check failed for {}: {}".format(store["name"], str(e)))
        
        logging.info("{} is still out of stock. Checking again in 2 seconds...".format(store["name"]))
        time.sleep(2)


def add_to_cart(store):
    """ Adds item to cart and proceeds to checkout """
    logging.info("Adding item to cart at {}...".format(store["name"]))
    try:
        check_for_captcha()
        WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
        ).click()
        logging.info("Item added to cart at {}!".format(store["name"]))
        proceed_to_checkout(store)
    except Exception as e:
        logging.error("Failed to add item to cart at {}: {}".format(store["name"], str(e)))


def main():
    """Runs stock checks with a controlled number of threads."""
    logging.info("Starting Restock Bot...")
    while True:
        with ThreadPoolExecutor(max_workers=min(3, len(config["websites"]))) as executor:
            executor.map(check_stock, config["websites"])
        logging.info("Sleeping for 3 seconds before checking again...")
        time.sleep(3)


if __name__ == "__main__":
    try:
        main()
    finally:
        driver.quit()
        logging.info("Browser closed.")
