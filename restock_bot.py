import os
import time
import logging
import yaml
import requests
import traceback
from threading import Thread
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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

driver = webdriver.Chrome(executable_path="/usr/local/bin/chromedriver", options=options)
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
    """ Checks if the product is in stock by checking if Add to Cart is disabled. """
    logging.info("Checking stock for {}...".format(store["name"]))
    driver.get(store["product_url"])

    retries = 3
    for attempt in range(retries):
        try:
            logging.info("Checking if 'Add to Cart' button is present...")

            # Wait for the "Add to Cart" button to load
            add_to_cart_button = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
            )

            logging.info("✅ 'Add to Cart' button found.")

            # Check if the button is disabled
            is_disabled = add_to_cart_button.get_attribute("disabled")

            if is_disabled:
                logging.info("⏳ {} is OUT OF STOCK (Button is disabled).".format(store["name"]))
            else:
                logging.info("🚀 {} is IN STOCK! Proceeding to checkout...".format(store["name"]))
                add_to_cart(store)
                return  # Stop checking after successful stock detection

        except Exception as e:
            logging.error("⚠️ Stock check failed for {} on attempt {}: {}".format(store["name"], attempt + 1, traceback.format_exc()))

    logging.error("❌ Giving up on {} after {} failed attempts.".format(store["name"], retries))


def add_to_cart(store):
    """ Adds item to cart and proceeds to checkout """
    logging.info("🛒 Adding item to cart at {}...".format(store["name"]))

    try:
        add_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
        )
        add_button.click()
        logging.info("✅ Item added to cart at {}!".format(store["name"]))

        proceed_to_checkout(store)
    except Exception as e:
        logging.error("❌ Failed to add item to cart at {}: {}".format(store["name"], e))

def proceed_to_checkout(store):
    """ Completes checkout process including login, payment, and final order placement """
    logging.info("💳 Proceeding to checkout at {}...".format(store["name"]))

    try:
        # Step 1: Click "View Cart and Checkout"
        WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["view_cart"]))
        ).click()
        logging.info("🛒 Clicked 'View Cart and Checkout'...")

        # Step 2: Click final "Checkout" button
        WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["checkout"]))
        ).click()
        logging.info("🛍️ Clicked final 'Checkout' button...")

        # Step 3: Handle Extra Login Step (Enter Password)
        logging.info("🔐 Checking for additional sign-in prompt...")
        time.sleep(2)  # Give time for login form to load

        password_field = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["checkout_password"]))
        )
        password_field.send_keys(PASSWORD)
        logging.info("🔑 Entered password...")

        sign_in_button = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["checkout_sign_in_button"]))
        )
        sign_in_button.click()
        logging.info("✅ Clicked 'Sign in with password' button...")

        # Step 4: Enter Payment Details
        WebDriverWait(driver, 2).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["payment"]["card_number"]))
        ).send_keys(CARD_NUMBER)
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["payment"]["expiry"]).send_keys(EXPIRY_DATE)
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["payment"]["cvv"]).send_keys(CVV)

        # Step 5: Click "Place Your Order" button
        logging.info("🛒 Clicking 'Place Your Order' button...")

        place_order_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["payment"]["submit_button"]))
        )
        place_order_button.click()

        logging.info("🎉 Order placed at {}!".format(store["name"]))

    except Exception as e:
        logging.error("❌ Checkout failed for {}: {}".format(store["name"], e))

def main():
    print("In Main..")
    for store in config["websites"]:  
        check_stock(store)

if __name__ == "__main__":
    main()

driver.quit()
logging.info("🛑 Browser closed.")
