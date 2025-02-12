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
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

driver = webdriver.Chrome(executable_path="/usr/local/bin/chromedriver", options=options)
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")


def check_for_captcha():
    """Detects and solves CAPTCHA if present using 2Captcha (only called during login/checkout)."""
    try:
        captcha_iframe = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='captcha']")
        if captcha_iframe:
            logging.warning("CAPTCHA detected! Attempting to solve automatically...")
            site_key = "your_target_site_key_here"  # Extract from HTML source
            page_url = driver.current_url

            # Request CAPTCHA solution from 2Captcha
            captcha_id_response = requests.post(
                "http://2captcha.com/in.php?key=" + API_KEY + "&method=userrecaptcha&googlekey=" +
                site_key + "&pageurl=" + page_url + "&json=1"
            ).json()

            if "request" not in captcha_id_response:
                logging.error("Failed to request CAPTCHA solving: " + str(captcha_id_response))
                return False

            captcha_id = captcha_id_response["request"]

            logging.info("Waiting for CAPTCHA solution...")
            time.sleep(10)  # Reduce wait time for faster solving

            # Retrieve solution (retry if necessary)
            for attempt in range(5):
                captcha_solution_response = requests.get(
                    "http://2captcha.com/res.php?key=" + API_KEY + "&action=get&id=" + str(captcha_id) + "&json=1"
                ).json()

                captcha_solution = captcha_solution_response.get("request", None)

                if captcha_solution in ["CAPCHA_NOT_READY", "ERROR_CAPTCHA_UNSOLVABLE", None]:
                    logging.warning("CAPTCHA solution not ready. Retrying in 3 seconds... (" + str(attempt + 1) + "/5)")
                    time.sleep(3)
                else:
                    break

            # Check if the solution is valid
            if not captcha_solution or captcha_solution in ["CAPCHA_NOT_READY", "ERROR_CAPTCHA_UNSOLVABLE"]:
                logging.error("Failed to solve CAPTCHA: " + str(captcha_solution))
                return False

            logging.info("CAPTCHA solved successfully!")

            # Ensure the CAPTCHA response field exists before setting the value
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "textarea#g-recaptcha-response"))
            )

            # Inject the CAPTCHA solution
            driver.execute_script(
                "document.querySelector('textarea#g-recaptcha-response').innerHTML = '" + captcha_solution + "';"
            )

            # Click verify or submit button if necessary
            try:
                verify_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                verify_button.click()
                logging.info("Clicked CAPTCHA verification button.")
            except:
                logging.info("No CAPTCHA verification button found. Proceeding.")

            return True
    except Exception as e:
        logging.error("Error solving CAPTCHA: " + str(e))


def check_stock(store):
    """ Continuously checks if the product is in stock by checking if Add to Cart is enabled. """
    logging.info("Checking stock for " + store["name"] + "...")
    driver.get(store["product_url"])

    while True:
        try:
            logging.info("Checking 'Add to Cart' button...")

            # Wait for the page to fully load before looking for the button
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
            )

            add_to_cart_button = driver.find_element(By.CSS_SELECTOR, store["selectors"]["add_to_cart"])

            if "disabled" not in add_to_cart_button.get_attribute("class"):
                logging.info(store["name"] + " is IN STOCK! Proceeding to checkout...")
                add_to_cart(store)
                return  # Stop checking once item is in stock
            else:
                logging.info(store["name"] + " is OUT OF STOCK. Retrying in 2 seconds...")

        except Exception as e:
            logging.error("Stock check failed for " + store["name"] + ": " + str(e))

        time.sleep(2)


def add_to_cart(store):
    """ Adds item to cart and proceeds to checkout """
    logging.info("Adding item to cart at " + store["name"] + "...")
    try:
        WebDriverWait(driver, 1).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
        ).click()
        logging.info("Item added to cart at " + store["name"] + "!")
        proceed_to_checkout(store)
    except Exception as e:
        logging.error("Failed to add item to cart at " + store["name"] + ": " + str(e))


def main():
    """Runs stock checks with controlled threading."""
    logging.info("Starting Restock Bot...")
    while True:
        with ThreadPoolExecutor(max_workers=1) as executor:  # Reduces parallel checks
            executor.map(check_stock, config["websites"])
        logging.info("Sleeping for 2 seconds before checking again...")
        time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    finally:
        driver.quit()
        logging.info("Browser closed.")
