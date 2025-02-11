import os
import time
import logging
import yaml
import requests
import traceback
from threading import Thread
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

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
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--disable-infobars")
options.add_argument("--mute-audio")
options.add_argument("--window-size=1920,1080")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

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
    """ Checks if the product is in stock for a given store. """
    logging.info("Checking stock for " + store["name"] + "...")
    driver.get(store["product_url"])

    retries = 3

    for attempt in range(retries):
        try:
            stock_element = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["stock"]))
            )
            stock_text = stock_element.text.lower()

            if "in stock" in stock_text:
                logging.info("🚀 " + store["name"] + " item is in stock! Proceeding to checkout...")
                add_to_cart(store)
                return
            else:
                logging.info("⏳ " + store["name"] + " is still out of stock...")

        except Exception as e:
            logging.error("⚠️ Stock check failed for " + store["name"] + " on attempt " + str(attempt + 1) + ": " + traceback.format_exc())

    logging.error("❌ Giving up on " + store["name"] + " after " + str(retries) + " failed attempts.")

def add_to_cart(store):
    """ Adds item to cart and proceeds to checkout """
    logging.info("🛒 Adding item to cart at " + store["name"] + "...")
    
    try:
        add_button = WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["add_to_cart"]))
        )
        add_button.click()
        logging.info("✅ Item added to cart at " + store["name"] + "!")

        proceed_to_checkout(store)
    except Exception as e:
        logging.error("❌ Failed to add item to cart at " + store["name"] + ": " + str(e))

def proceed_to_checkout(store):
    """ Completes checkout process including payment """
    logging.info("💳 Proceeding to checkout at " + store["name"] + "...")
    driver.get(store["checkout_url"])

    try:
        WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, store["selectors"]["checkout"]))
        ).click()

        # Handling CAPTCHA
        if store["selectors"].get("captcha"):
            bypass_captcha(store)

        # Enter Payment Details
        WebDriverWait(driver, 2).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, store["selectors"]["payment"]["card_number"]))
        ).send_keys(CARD_NUMBER)

        driver.find_element(By.CSS_SELECTOR, store["selectors"]["payment"]["expiry"]).send_keys(EXPIRY_DATE)
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["payment"]["cvv"]).send_keys(CVV)

        # Submit Order
        driver.find_element(By.CSS_SELECTOR, store["selectors"]["payment"]["submit_button"]).click()
        logging.info("🎉 Order placed at " + store["name"] + "!")
    
    except Exception as e:
        logging.error("❌ Checkout failed for " + store["name"] + ": " + str(e))

def bypass_captcha(store):
    """ Automatically solves CAPTCHA using an external service. """
    logging.info("⚠️ CAPTCHA detected on " + store["name"] + ", solving...")

    captcha_iframe = driver.find_element(By.CSS_SELECTOR, store["selectors"]["captcha"])
    captcha_src = captcha_iframe.get_attribute("src")

    api_key = config["settings"]["captcha_solver_api_key"]
    response = requests.post(
        "http://2captcha.com/in.php",
        data={"key": api_key, "method": "userrecaptcha", "googlekey": captcha_src, "pageurl": store["checkout_url"]}
    )
    
    captcha_id = response.text.split('|')[1]
    time.sleep(10)  # Wait for solution

    response = requests.get("http://2captcha.com/res.php?key=" + api_key + "&action=get&id=" + captcha_id)
    captcha_solution = response.text.split('|')[1]

    driver.execute_script("document.getElementById('g-recaptcha-response').innerHTML = '" + captcha_solution + "';")
    logging.info("✅ CAPTCHA bypassed on " + store["name"] + "!")

# Run the bot for each store using multi-threading
threads = []
for store in config["websites"]:
    thread = Thread(target=check_stock, args=(store,))
    thread.start()
    threads.append(thread)

# Wait for all threads to finish
for thread in threads:
    thread.join()

# Close browser after execution
driver.quit()
logging.info("🛑 Browser closed.")

finally:
    driver.quit()  # Close browser
    logging.info("🛑 Browser closed.")
