from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from sqlalchemy.orm import Session
import time
import pandas as pd
import logging
import sys
from database.models import Outlet
from database.crud import create_outlet


# Configure logging to write to both file and console
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler('subway_scraper.log'),
                        logging.StreamHandler(sys.stdout)
                    ])


def scrape_subway_outlets(db: Session, export_csv=False):
    driver = None
    error_count = 0
    try:
        # Initialize Chrome with options
        options = webdriver.ChromeOptions()
        options.add_argument('--disable-notifications')
        options.add_argument('--start-maximized')
        # Add these additional options for stability
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        driver = webdriver.Chrome(options=options)

        # Increased timeout for loading pages
        wait = WebDriverWait(driver, 30)  # Increased from 20 to 30 seconds

        logging.info("Starting to scrape Subway outlets")
        driver.get("https://subway.com.my/find-a-subway")

        # Wait for page to fully load
        time.sleep(5)  # Give the page more time to load completely

        # Take a screenshot to debug
        driver.save_screenshot("page_loaded.png")
        logging.info("Saved initial page screenshot")

        # Optional popup handling - won't fail if no popup exists
        try:
            logging.info("Checking for popups - this step is optional")
            # Look for popup elements but with visibility check
            popups = driver.find_elements(By.CSS_SELECTOR,
                                          ".modal-close, .popup-close, .close-button, button[class*='close']")

            for popup in popups:
                # Only try to click if element is displayed and enabled
                if popup.is_displayed() and popup.is_enabled():
                    try:
                        logging.info(
                            "Found visible popup, attempting to close")
                        popup.click()
                        logging.info("Popup closed successfully")
                        time.sleep(1)
                        break
                    except Exception as e:
                        logging.info(f"Could not click popup: {str(e)}")
            else:
                logging.info("No interactable popups found")
        except Exception as e:
            # Don't fail the entire scraper just because of popup handling
            logging.info(f"Skipping popup handling: {str(e)}")

        # Try multiple selector strategies for city selection
        selectors = [
            "div.location_left",
            "div[class*='location_left']",
            "div.city-selector",
            "div[class*='city-selector']",
            "div.dropdown-toggle",
            "//div[contains(@class, 'city') and contains(@class, 'selector')]"
        ]

        clicked = False
        for selector in selectors:
            try:
                logging.info(f"Trying selector: {selector}")
                if selector.startswith("//"):
                    # XPath selector
                    element = wait.until(
                        EC.element_to_be_clickable((By.XPATH, selector)))
                else:
                    # CSS selector
                    element = wait.until(EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, selector)))

                # Try JavaScript click if regular click might fail
                driver.execute_script(
                    "arguments[0].scrollIntoView(true);", element)
                time.sleep(1)

                # Take screenshot before clicking
                driver.save_screenshot("before_click.png")

                try:
                    element.click()
                except:
                    # If regular click fails, try JavaScript click
                    driver.execute_script("arguments[0].click();", element)

                clicked = True
                logging.info(
                    f"Successfully clicked city selector with: {selector}")
                time.sleep(3)  # Wait longer after clicking
                break
            except Exception as e:
                logging.warning(f"Failed with selector {selector}: {str(e)}")

        if not clicked:
            error_msg = "Could not click city selector with any selector"
            logging.error(error_msg)
            print(f"ERROR: {error_msg}")
            # Take screenshot to see what's happening
            driver.save_screenshot("failed_city_selector.png")
            raise Exception(error_msg)

        # Scroll to Kuala Lumpur in the menu
        try:
            city_menu = wait.until(
                EC.presence_of_element_located(
                    (By.ID, "fp_locationlist"))
            )
            # Take screenshot of city menu before scrolling
            driver.save_screenshot("city_menu_before_scroll.png")

            # Adjust scroll position
            driver.execute_script("arguments[0].scrollTop = 500", city_menu)
            logging.info("Scrolled city menu")
            time.sleep(2)  # Wait after scrolling

            # Take screenshot after scrolling
            driver.save_screenshot("city_menu_after_scroll.png")
        except (TimeoutException, NoSuchElementException) as e:
            logging.error(f"Failed to scroll city menu: {str(e)}")
            raise

        # Select Kuala Lumpur - with multiple fallback strategies
        try:
            # Try multiple selectors for finding Kuala Lumpur
            city_selectors = [
                "//div[text()='Kuala Lumpur']",
                "//div[contains(text(), 'Kuala Lumpur')]",
                "//span[contains(text(), 'Kuala Lumpur')]",
                "//li[contains(text(), 'Kuala Lumpur')]",
                "//a[contains(text(), 'Kuala Lumpur')]",
                "//div[contains(@class, 'infoboxcontent') and contains(text(), 'Kuala')]",
                "//div[contains(@class, 'infoboxcontent') and contains(text(), 'Kuala')]",
                "//div[contains(@class, 'infoboxcontent') and contains(text(), 'KL')]",
                "//div[contains(@class, 'infoboxcontent') and contains(text(), 'KUL')]",
                "//div[contains(@class, 'infoboxcontent') and contains(text(), 'KUALA')]",


            ]

            city_selected = False
            for selector in city_selectors:
                try:
                    logging.info(
                        f"Trying to find Kuala Lumpur with: {selector}")
                    # Use a shorter timeout (10s) for each attempt
                    city_element = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )

                    # Take screenshot before clicking
                    driver.save_screenshot("before_city_click.png")

                    # Try regular click
                    try:
                        city_element.click()
                    except Exception:
                        # If regular click fails, try JS click
                        driver.execute_script(
                            "arguments[0].click();", city_element)

                    logging.info(f"Selected Kuala Lumpur with: {selector}")
                    city_selected = True
                    time.sleep(3)  # Wait after selection
                    break
                except Exception as e:
                    logging.warning(
                        f"Failed with selector {selector}: {str(e)}")

            # If direct selection failed, try alternative approach
            if not city_selected:
                logging.info("Trying alternative city selection approaches")

                # Approach 1: Try clicking by index (e.g., the 3rd city in the list)
                try:
                    city_items = city_menu.find_elements(
                        By.CSS_SELECTOR, "div.city-item")
                    if len(city_items) > 0:
                        # Log what cities are available for debugging
                        # Get first 10
                        city_texts = [item.text for item in city_items[:10]]
                        logging.info(f"Found cities: {city_texts}")

                        # Try to find one with "Kuala" in the text
                        kl_items = [
                            item for item in city_items if "Kuala" in item.text]
                        if kl_items:
                            kl_items[0].click()
                            logging.info("Selected Kuala Lumpur by text match")
                            city_selected = True
                        elif len(city_items) >= 3:  # Assuming KL might be the 3rd item
                            city_items[2].click()
                            logging.info("Selected city by index position")
                            city_selected = True
                except Exception as e:
                    logging.warning(f"Alternative selection failed: {str(e)}")

            if not city_selected:
                raise Exception(
                    "Could not select Kuala Lumpur with any strategy")

        except Exception as e:
            logging.error(f"Failed to select Kuala Lumpur: {str(e)}")
            # Take screenshots of what we see
            driver.save_screenshot("city_selection_failed.png")
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
                    error_count += 1
                    error_msg = f"Error processing outlet {i+1}: {str(e)}"
                    logging.error(error_msg)
                    print(f"ERROR: {error_msg}")

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

        # Print error summary if any errors occurred
        if error_count > 0:
            print(
                f"⚠️ ATTENTION: {error_count} errors occurred during scraping. Check the log file for details.")

        # Export to CSV if requested
        if export_csv and locations:
            try:
                df = pd.DataFrame(locations)
                df.to_csv('subway_locations.csv', index=False)
                logging.info(f"Exported {len(df)} locations to CSV!")
                print(f"Exported {len(df)} locations to CSV!")
            except Exception as e:
                error_msg = f"Failed to export to CSV: {str(e)}"
                logging.error(error_msg)
                print(f"ERROR: {error_msg}")

        return locations

    except Exception as e:
        error_msg = f"Fatal error in scraper: {str(e)}"
        logging.error(error_msg)
        print(f"FATAL ERROR: {error_msg}")
        raise
    finally:
        if driver:
            driver.quit()
            logging.info("WebDriver closed")
