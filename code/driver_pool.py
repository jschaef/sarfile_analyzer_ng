
import queue
import threading
import os
import streamlit as st
from selenium import webdriver
from selenium.webdriver.firefox.options import Options

class BokehDriverPool:
    def __init__(self, max_drivers=4):
        self.drivers = queue.Queue()
        self.max_drivers = max_drivers
        self.current_drivers = 0
        self.lock = threading.Lock()
        self._init_done = False

    def _ensure_geckodriver(self):
        if not self._init_done:
            try:
                import geckodriver_autoinstaller
                geckodriver_autoinstaller.install()
                self._init_done = True
            except Exception:
                pass

    def _create_driver(self):
        self._ensure_geckodriver()
        
        firefox_options = Options()
        firefox_options.add_argument('--headless')
        firefox_options.add_argument('--disable-gpu')
        firefox_options.add_argument('--no-sandbox')
        firefox_options.add_argument('--disable-dev-shm-usage')
        # Force 1:1 pixel ratio for consistent sizing
        firefox_options.set_preference("layout.css.devPixelsPerUnit", "1.0")
        
        return webdriver.Firefox(options=firefox_options)

    def acquire(self):
        """Acquire a driver from the pool or create a new one."""
        while True:
            driver = None
            try:
                # Try to get an existing driver without waiting
                driver = self.drivers.get_nowait()
            except queue.Empty:
                # If no driver available, check if we can create a new one
                with self.lock:
                    if self.current_drivers < self.max_drivers:
                        try:
                            driver = self._create_driver()
                            self.current_drivers += 1
                            return driver
                        except Exception as e:
                            st.error(f"Failed to start Firefox: {e}")
                            return None
                
                # Otherwise, wait for one to be returned
                driver = self.drivers.get()

            # Check if driver is still alive/responsive
            try:
                # Simple check: try to get window handles
                if driver and driver.service.process.poll() is None:
                    return driver
            except Exception:
                pass
            
            # Driver is dead, decrement count and try again
            if driver:
                with self.lock:
                    self.current_drivers -= 1
                try:
                    driver.quit()
                except Exception:
                    pass

    def release(self, driver):
        """Return a driver to the pool."""
        if driver:
            self.drivers.put(driver)

@st.cache_resource
def get_driver_pool():
    # Use ~50% of CPUs for the pool to avoid over-consumption, max 4
    cpu_count = os.cpu_count() or 4
    num_drivers = max(1, min(int(cpu_count * 0.5), 4))
    return BokehDriverPool(max_drivers=num_drivers)
