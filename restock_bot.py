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

            captcha_id = requests.post(
                f"http://2captcha.com/in.php?key={API_KEY}&method=userrecaptcha&googlekey={site_key}&pageurl={page_url}&json=1"
            ).json().get("request")

            logging.info("Waiting for CAPTCHA solution...")
            time.sleep(10)  # Reduce wait time from 15 to 10 seconds

            captcha_solution = requests.get(
                f"http://2captcha.com/res.php?key={API_KEY}&action=get&id={captcha_id}&json=1"
            ).json().get("request")

            if captcha_solution:
                logging.info("CAPTCHA solved successfully!")
                driver.execute_script(
                    f"document.getElementById('g-recaptcha-response').innerHTML = '{captcha_solution}';"
                )

                # Check if a verify button needs to be clicked
                try:
                    verify_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                    verify_button.click()
                    logging.info("Clicked CAPTCHA verification button.")
                except:
                    logging.info("No CAPTCHA verification button found. Proceeding.")

                return True
            else:
                logging.error("Failed to solve CAPTCHA.")
                return False
    except Exception as e:
        logging.error("Error solving CAPTCHA: {}".format(str(e)))



def check_stock(store):
    """ Continuously checks if the product is in stock by checking if Add to Cart is enabled. """
    logging.info("Checking stock for {}...".format(store["name"]))
    driver.get(store["product_url"])

    while True:
        try:
            check_for_captcha()

            logging.info("Checking 'Add to Cart' button...")
            add_to_cart_button = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
            )

            logging.info("{} is IN STOCK! Proceeding to checkout...".format(store["name"]))
            add_to_cart(store)
            return  # Stop checking once item is in stock

        except Exception:
            logging.info("{} is still out of stock. Retrying in 2 seconds...".format(store["name"]))
        
        time.sleep(2)  # Keep checking every 2 seconds



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


def proceed_to_checkout(store):
    """ Completes checkout process. """
    logging.info("Proceeding to checkout at {}...".format(store["name"]))
    try:
        check_for_captcha()
        WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["view_cart"]))
        ).click()
        WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["checkout"]))
        ).click()

        # If login is required at checkout, re-enter credentials
        try:
            password_field = WebDriverWait(driver, 1).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["checkout_password"]))
            )
            password_field.send_keys(PASSWORD)

            WebDriverWait(driver, 1).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["checkout_sign_in_button"]))
            ).click()
            logging.info("Re-logged into checkout page.")
        except Exception:
            logging.info("No login required at checkout.")

        WebDriverWait(driver, 1).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["payment"]["card_number"]))
        ).send_keys(CARD_NUMBER)
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["payment"]["expiry"]).send_keys(EXPIRY_DATE)
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["payment"]["cvv"]).send_keys(CVV)
        
        WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["payment"]["submit_button"]))
        ).click()
        
        logging.info("Order placed at {}!".format(store["name"]))
    except Exception as e:
        logging.error("Checkout failed for {}: {}".format(store["name"], str(e)))


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
