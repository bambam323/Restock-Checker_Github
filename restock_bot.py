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
import threading

# Disable warnings & increase connection pool size
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables (Login & Payment Info)
load_dotenv()
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
CARD_NUMBER = os.getenv("CARD_NUMBER")
EXPIRY_DATE = os.getenv("EXPIRY_DATE")
CVV = os.getenv("CVV")

# Target Login URL
LOGIN_URL = "https://www.target.com/login?client_id=ecom-web-1.0.0&ui_namespace=ui-default&back_button_action=browser&keep_me_signed_in=true&kmsi_default=false&actions=create_session_signin"

# Load configuration file
try:
    with open("config.yaml", "r") as file:
        config = yaml.safe_load(file)
except Exception as e:
    logging.error("❌ Failed to load config.yaml: " + str(e))
    exit(1)

# Configure logging
logging.basicConfig(filename="restock_bot.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Setup Chrome WebDriver (Compatible with Older Versions)
options = webdriver.ChromeOptions()
options.add_argument("--headless")  # Disable this line if CAPTCHA is happening too often
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("start-maximized")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)


def create_driver():
    """Creates and returns a new WebDriver instance."""

    # With v4.28.1 of Selenium, it will automatically populate the driver here for you
    driver = webdriver.Chrome()

    # With older versions of Selenium and webdriver-manager, this is the oldest Chrome driver supported (not ideal)
    driver = webdriver.Chrome(ChromeDriverManager(version='114.0.5735.90').install())

    #Uncomment the line below for older versions of Selenium in conjunction with webdriver-manager
    driver = webdriver.Chrome(executable_path="/usr/local/bin/chromedriver", options=options)
    #driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def sign_in(driver):
    """Logs into the Target account before checking stock."""
    logging.info("🔑 Signing into Target account...")

    try:
        driver.get(LOGIN_URL)

        # Step 0: Click first "Sign In" button
        account_sign_in = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#account-sign-in"))
        )
        account_sign_in.click()
        logging.info("✅ Clicked first sign in button")

        # Step 1: Click second "Sign In" button
        account_sign_in2 = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "button[data-test='accountNav-signIn']"))
        )
        account_sign_in2.click()
        logging.info("✅ Clicked second sign in button")


        # Step 2: Enter email
        email_input = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input#username"))
        )
        email_input.send_keys(EMAIL)
        logging.info("✅ Entered email")

        # Step 3: Enter password
        password_input = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input#password"))
        )
        password_input.send_keys(PASSWORD)
        logging.info("✅ Entered password")

        # Step 4: Click "Sign in with password" (AFTER email & password are filled)
        sign_in_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[id='login']"))
        )
        sign_in_button.click()
        logging.info("✅ Clicked 'Sign in with password' button")

        # Ensure login was successful by checking if the account icon appears
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "use[href='/icons/Account.svg#Account']"))
        )
        logging.info("✅ Successfully logged in!")

    except Exception as e:
        logging.error("❌ Failed to log in: " + str(e))
        logging.error("📜 Full Exception Traceback:\n" + traceback.format_exc())
        driver.quit()
        exit(1)  # Stop the bot if login fails



def check_stock(store):
    """ Continuously checks if the product is in stock. """
    logging.info("🔍 Checking stock for " + store["name"] + "...")

    driver = create_driver()  # Start a separate WebDriver instance for each product
    sign_in(driver)  # Ensure login before checking stock

    while True:
        try:
            driver.get(store["product_url"])
            logging.info("⏳ Waiting for page to fully load... (" + store["name"] + ")")
            time.sleep(3)

            logging.info("📌 Checking 'Add to Cart' button... (" + store["name"] + ")")
            add_to_cart_button = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
            )

            if add_to_cart_button.is_enabled():
                logging.info("🚀 " + store["name"] + " is IN STOCK! Verifying price...")

                if check_price(store, driver):
                    logging.info("✅ Price verified! Proceeding to checkout... (" + store["name"] + ")")
                    checkout_thread = threading.Thread(target=add_to_cart, args=(store, driver))
                    checkout_thread.start()
                    return  # Stop checking once an item is being checked out

                else:
                    logging.info("⚠️ " + store["name"] + " is too expensive. Waiting for price drop.")

            else:
                logging.info("⏳ " + store["name"] + " is still OUT OF STOCK. Refreshing soon...")

        except Exception as e:
            logging.error("❌ Stock check failed for " + store["name"] + ": " + str(e))
            logging.error("📜 Full Exception Traceback:\n" + traceback.format_exc())

        time.sleep(3)


def check_price(store, driver):
    """Checks if the product price is within the allowed budget before purchase."""
    try:
        price_element = WebDriverWait(driver, 2).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["price"]))
        )
        price_text = price_element.text.replace("$", "").strip()
        price = float(price_text)

        if price > store["max_price"]:
            logging.warning(store["name"] + " is too expensive! Price: $" + str(price) + ", Max Allowed: $" + str(store["max_price"]))
            return False
        else:
            logging.info(store["name"] + " is within budget! Price: $" + str(price))
            return True
    except Exception as e:
        logging.error("⚠️ Failed to check price for " + store["name"] + ". Skipping.")
        return False


def add_to_cart(store, driver):
    """ Adds item to cart and interacts with the 'Added to Cart' modal before proceeding to checkout """
    logging.info("🛒 Adding item to cart at " + store["name"] + "...")

    try:
        add_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
        )

        add_button.click()
        logging.info("✅ Item added to cart at " + store["name"] + "! Waiting for confirmation...")

        modal = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-test='content-wrapper']"))
        )
        logging.info("🛍️ 'Added to Cart' modal detected!")

        checkout_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.LINK_TEXT, "View cart & check out"))
        )
        checkout_button.click()
        logging.info("✅ Navigated to cart page. Proceeding to checkout...")

        proceed_to_checkout(store, driver)

    except Exception as e:
        logging.error("❌ Failed to add item to cart at " + store["name"] + ": " + str(e))


def proceed_to_checkout(store, driver):
    """Completes checkout process."""
    logging.info("🚀 Proceeding to checkout at " + store["name"] + "...")

    try:
        WebDriverWait(driver, 3).until(
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


def main():
    logging.info("🚀 Starting Restock Bot...")
    #check_stock(config["websites"][0])

    threads = [threading.Thread(target=check_stock, args=(store,)) for store in config["websites"]]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    try:
        main()
    finally:
        logging.info("🛑 Browser closed.")

if __name__ == "__main__":
    try:
        main()
    finally:
        logging.info("🛑 Browser closed.")
