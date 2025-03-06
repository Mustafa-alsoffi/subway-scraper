from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from sqlalchemy.orm import Session
import time
import pandas as pd
import logging
from database.models import Outlet
from database.crud import create_outlet


# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='subway_scraper.log')


def scrape_subway_outlets(db: Session, export_csv=False):
    driver = None
    try:
        # Initialize Chrome with options
        options = webdriver.ChromeOptions()
        options.add_argument('--disable-notifications')
        options.add_argument('--start-maximized')
        driver = webdriver.Chrome(options=options)

        # Increased timeout for loading pages
        wait = WebDriverWait(driver, 20)

        logging.info("Starting to scrape Subway outlets")
        driver.get("https://subway.com.my/find-a-subway")

        # Handle popup if it appears
        try:
            popup_close = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".modal-close, .popup-close, .close-button"))
            )
            popup_close.click()
            logging.info("Popup detected and closed")
        except TimeoutException:
            logging.info("No popup detected")

        # Handle city selection with scroll
        try:
            wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "div.city-selector"))
            ).click()
            logging.info("City selector clicked")
        except (TimeoutException, NoSuchElementException) as e:
            logging.error(f"Failed to click city selector: {str(e)}")
            raise

        # Scroll to Kuala Lumpur in the menu
        try:
            city_menu = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.city-menu"))
            )
            # Adjust scroll position
            driver.execute_script("arguments[0].scrollTop = 500", city_menu)
            logging.info("Scrolled city menu")
        except (TimeoutException, NoSuchElementException) as e:
            logging.error(f"Failed to scroll city menu: {str(e)}")
            raise

        # Select Kuala Lumpur - more robust selector
        try:
            wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//div[contains(text(), 'Kuala Lumpur')]"))
            ).click()
            logging.info("Selected Kuala Lumpur")
            time.sleep(2)  # Increased wait time for filter to apply
        except (TimeoutException, NoSuchElementException) as e:
            logging.error(f"Failed to select Kuala Lumpur: {str(e)}")
            raise

        # Handle pagination with dynamic loading
        processed = set()
        locations = []
        page_count = 0

        while True:
            page_count += 1
            logging.info(f"Processing page {page_count}")

            try:
                # Wait longer for outlet cards to load
                wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div.outlet-card"))
                )
            except TimeoutException:
                logging.warning("No outlets found or loading timed out")
                break

            # Extract outlet data
            outlets = driver.find_elements(By.CSS_SELECTOR, "div.outlet-card")
            logging.info(f"Found {len(outlets)} outlets on current page")

            for i, outlet in enumerate(outlets):
                try:
                    # Extract basic information
                    name = outlet.find_element(By.CSS_SELECTOR, "h3").text
                    address = outlet.find_element(
                        By.CSS_SELECTOR, ".address").text

                    # Skip if already processed
                    if name in processed:
                        continue

                    logging.info(f"Processing outlet: {name}")

                    # Extract optional fields with error handling
                    try:
                        phone = outlet.find_element(
                            By.CSS_SELECTOR, ".phone").text
                    except NoSuchElementException:
                        phone = None
                        logging.debug(f"No phone found for {name}")

                    try:
                        hours = outlet.find_element(
                            By.CSS_SELECTOR, ".hours").text
                    except NoSuchElementException:
                        hours = None
                        logging.debug(f"No hours found for {name}")

                    # Extract map links
                    try:
                        waze_link = outlet.find_element(
                            By.CSS_SELECTOR, ".waze a").get_attribute("href")
                    except NoSuchElementException:
                        waze_link = None
                        logging.debug(f"No Waze link found for {name}")

                    try:
                        google_map_link = outlet.find_element(
                            By.CSS_SELECTOR, ".google-map a").get_attribute("href")
                    except NoSuchElementException:
                        google_map_link = None
                        logging.debug(f"No Google Maps link found for {name}")

                    # Extract coordinates if available
                    try:
                        latitude = outlet.get_attribute("data-latitude")
                        longitude = outlet.get_attribute("data-longitude")
                    except Exception:
                        latitude = None
                        longitude = None
                        logging.debug(f"No coordinates found for {name}")

                    # Extract location ID if available
                    try:
                        location_id = outlet.get_attribute("data-id")
                    except Exception:
                        location_id = None
                        logging.debug(f"No location ID found for {name}")

                    # Save to database
                    try:
                        create_outlet(db, name, address,
                                      phone, hours, waze_link)
                        processed.add(name)
                        logging.info(
                            f"Successfully saved outlet {name} to database")
                    except Exception as e:
                        logging.error(
                            f"Failed to save {name} to database: {str(e)}")

                    # Add to locations list for CSV export
                    locations.append({
                        'id': location_id,
                        'name': name,
                        'address': address,
                        'hours': hours,
                        'phone': phone,
                        'latitude': latitude,
                        'longitude': longitude,
                        'google_map': google_map_link,
                        'waze_map': waze_link
                    })
                except Exception as e:
                    logging.error(f"Error processing outlet {i+1}: {str(e)}")

            # Improved infinite scroll pagination with retry
            scroll_attempts = 0
            max_scroll_attempts = 3
            last_height = driver.execute_script(
                "return document.body.scrollHeight")

            while scroll_attempts < max_scroll_attempts:
                # Scroll down
                driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)  # Increased wait time for content to load

                # Check if we've reached the end
                new_height = driver.execute_script(
                    "return document.body.scrollHeight")
                if new_height == last_height:
                    scroll_attempts += 1
                else:
                    break  # Content loaded, continue scraping

            if scroll_attempts == max_scroll_attempts:
                logging.info("Reached end of scrolling, all outlets processed")
                break

        logging.info(
            f"Scraping completed. Processed {len(processed)} unique outlets.")

        # Export to CSV if requested
        if export_csv and locations:
            try:
                df = pd.DataFrame(locations)
                df.to_csv('subway_locations.csv', index=False)
                logging.info(f"Exported {len(df)} locations to CSV!")
                print(f"Exported {len(df)} locations to CSV!")
            except Exception as e:
                logging.error(f"Failed to export to CSV: {str(e)}")

        return locations

    except Exception as e:
        logging.error(f"Fatal error in scraper: {str(e)}")
        raise
    finally:
        if driver:
            driver.quit()
            logging.info("WebDriver closed")
