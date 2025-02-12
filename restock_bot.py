import os
import time
import logging
import yaml
import traceback
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor

# Load environment variables (Login & Payment Info)
load_dotenv()
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
CARD_NUMBER = os.getenv("CARD_NUMBER")
EXPIRY_DATE = os.getenv("EXPIRY_DATE")
CVV = os.getenv("CVV")

# Mask sensitive data for logging
masked_email = EMAIL[:2] + "****@****.com"

# Load configuration file
try:
    with open("config.yaml", "r") as file:
        config = yaml.safe_load(file)
except Exception as e:
    logging.error("❌ Failed to load config.yaml: " + str(e))
    exit(1)

# Configure logging
logging.basicConfig(filename="restock_bot.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Setup Chrome WebDriver (Compatible with older Selenium)
options = webdriver.ChromeOptions()
options.add_argument("--headless")  # Runs Chrome without UI
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")  # Anti-bot detection bypass
options.add_argument("start-maximized")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

driver = webdriver.Chrome(executable_path="/usr/local/bin/chromedriver", options=options)
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")


def check_for_captcha():
    """Detects if a CAPTCHA appears and logs a warning."""
    try:
        captcha_iframe = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='captcha']")
        if captcha_iframe:
            logging.warning("🚨 CAPTCHA detected! Manual intervention required.")
            input("Solve the CAPTCHA manually, then press Enter to continue...")
    except Exception:
        pass


def login(store):
    """ Logs into the store securely. """
    logging.info("🔑 Logging into {} with {}...".format(store['name'], masked_email))
    driver.get(store["login_url"])
    try:
        check_for_captcha()
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["login"]["email"])))
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["login"]["email"]).send_keys(EMAIL)
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["login"]["password"]).send_keys(PASSWORD)
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["login"]["login_button"]).click()
        WebDriverWait(driver, 5).until(EC.url_changes(store["login_url"]))
        logging.info("✅ Login successful for {}!".format(store["name"]))
    except Exception as e:
        logging.error("❌ Login failed for {}: {}".format(store["name"], str(e)))


def check_price(store):
    """Checks if the product price is within the allowed budget before purchase."""
    try:
        price_element = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["price"]))
        )
        price_text = price_element.text.replace("$", "").strip()
        price = float(price_text)

        if price > store["max_price"]:
            logging.warning("💰 {} is too expensive! Price: ${}, Max Allowed: ${}".format(
                store["name"], price, store["max_price"]
            ))
            return False  # Don't proceed with checkout
        else:
            logging.info("✅ {} is within budget! Price: ${}".format(store["name"], price))
            return True  # Proceed with checkout
    except Exception as e:
        logging.error("⚠️ Failed to check price for {}: {}".format(store["name"], str(e)))
        return False  # Assume price is too high if we can't read it


def check_stock(store):
    """ Continuously checks if the product is in stock by checking if Add to Cart is enabled. """
    logging.info("🔍 Checking stock for {}...".format(store["name"]))
    driver.get(store["product_url"])
    
    while True:
        try:
            check_for_captcha()

            # Check price before proceeding
            if not check_price(store):
                return  # Skip if price is too high

            logging.info("Checking 'Add to Cart' button...")
            add_to_cart_button = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
            )
            if not add_to_cart_button.get_attribute("disabled"):
                logging.info("🚀 {} is IN STOCK! Proceeding to checkout...".format(store["name"]))
                add_to_cart(store)
                return  # Stop checking after successful stock detection
            else:
                logging.info("⏳ {} is OUT OF STOCK.".format(store["name"]))
        except Exception as e:
            logging.error("⚠️ Stock check failed for {}: {}".format(store["name"], str(e)))
        
        logging.info("🔄 {} is still out of stock. Checking again in 3 seconds...".format(store["name"]))
        time.sleep(3)


def add_to_cart(store):
    """ Adds item to cart and proceeds to checkout """
    logging.info("🛒 Adding item to cart at {}...".format(store["name"]))
    try:
        check_for_captcha()
        WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
        ).click()
        logging.info("✅ Item added to cart at {}!".format(store["name"]))
        proceed_to_checkout(store)
    except Exception as e:
        logging.error("❌ Failed to add item to cart at {}: {}".format(store["name"], str(e)))


def proceed_to_checkout(store):
    """ Completes checkout process including login, payment, and final order placement """
    logging.info("💳 Proceeding to checkout at {}...".format(store["name"]))
    try:
        check_for_captcha()
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
        
        logging.info("🎉 Order placed at {}!".format(store["name"]))
    except Exception as e:
        logging.error("❌ Checkout failed for {}: {}".format(store["name"], str(e)))


def main():
    """ Runs stock checks concurrently for all stores. """
    logging.info("🚀 Starting Restock Bot...")
    with ThreadPoolExecutor(max_workers=min(3, len(config["websites"]))) as executor:
        executor.map(check_stock, config["websites"])


if __name__ == "__main__":
    try:
        main()
    finally:
        driver.quit()
        logging.info("🛑 Browser closed.")
