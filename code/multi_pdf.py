#!/usr/bin/python3
from pypdf import PdfWriter
from os import remove, path
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import time
from PIL import Image


def _export_worker(figures_chunk, shared_progress_list):
    """Worker function to export a chunk of Bokeh figures to PDF bytes using a single driver instance."""
    from bokeh.io import export_png
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options
    
    firefox_options = Options()
    firefox_options.add_argument('--headless')
    firefox_options.add_argument('--disable-gpu')
    firefox_options.add_argument('--no-sandbox')
    firefox_options.add_argument('--disable-dev-shm-usage')
    firefox_options.set_preference("layout.css.devPixelsPerUnit", "1.0")

    driver = webdriver.Firefox(options=firefox_options)
    pdf_bytes_list = []
    
    try:
        for fig in figures_chunk:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_png:
                png_path = tmp_png.name
            
            try:
                export_png(fig, filename=png_path, webdriver=driver)

                with Image.open(png_path) as image:
                    if image.mode == 'RGBA':
                        image = image.convert('RGB')
                    
                    pdf_buffer = io.BytesIO()
                    image.save(pdf_buffer, format='PDF', resolution=100.0)
                    pdf_bytes_list.append(pdf_buffer.getvalue())
            finally:
                if os.path.exists(png_path):
                    os.remove(png_path)
            
            # Signal progress by appending to shared list (thread-safe enough for count)
            shared_progress_list.append(1)
                    
        return pdf_bytes_list
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def create_multi_pdf_from_bokeh_figures(bokeh_figures: list, st_progress_bar=None):
    """Create a multi-page PDF from a list of Bokeh figures using parallel workers.

    Processing is parallelized based on CPU count (~75% of available CPUs).
    UI updates are handled in the main thread to avoid NoSessionContext errors.
    """
    if not bokeh_figures:
        return None

    num_figures = len(bokeh_figures)
    
    # Calculate workers: ~75% of CPUs, max 8
    cpu_count = os.cpu_count() or 4
    num_workers = max(1, min(int(cpu_count * 0.75), 8))
    num_workers = min(num_workers, num_figures)
    
    # Ensure geckodriver is ready
    try:
        import geckodriver_autoinstaller
        geckodriver_autoinstaller.install()
    except Exception:
        pass

    # Split figures into chunks
    chunk_size = (num_figures + num_workers - 1) // num_workers
    chunks = [bokeh_figures[i:i + chunk_size] for i in range(0, num_figures, chunk_size)]
    
    # Shared list to track progress across threads
    shared_progress = []
    all_pdf_bytes = []
    
    # Execute in background
    with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
        futures = [executor.submit(_export_worker, chunk, shared_progress) for chunk in chunks]
        
        # While threads are working, update the progress bar from the MAIN thread
        while any(not f.done() for f in futures):
            if st_progress_bar:
                current_count = len(shared_progress)
                percent = min(1.0, current_count / num_figures)
                st_progress_bar.progress(percent, text=f"Exporting diagram {current_count} of {num_figures}...")
            time.sleep(0.5) # Poll every 500ms
            
        # All done, collect results in order
        for future in futures:
            all_pdf_bytes.extend(future.result())

    # Final progress update
    if st_progress_bar:
        st_progress_bar.progress(1.0, text=f"Merging {num_figures} pages into final PDF...")

    # Merge into final PDF
    merger = PdfWriter()
    try:
        for pdf_data in all_pdf_bytes:
            merger.append(io.BytesIO(pdf_data))

        temp_output_fd, temp_output_path = tempfile.mkstemp(suffix='.pdf')
        os.close(temp_output_fd)
        
        with open(temp_output_path, 'wb') as output:
            merger.write(output)
            
        return temp_output_path
    finally:
        merger.close()
