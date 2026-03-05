#!/usr/bin/python3
from pypdf import PdfWriter
from os import remove, path
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
import io
import time
from PIL import Image


def _export_worker(figures_chunk, worker_id):
    """Worker function to export a chunk of Bokeh figures to PDF bytes using a single driver instance."""
    from bokeh.io import export_png
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.firefox.service import Service
    
    # Try to ensure geckodriver exists (once per worker is enough)
    try:
        import geckodriver_autoinstaller
        geckodriver_autoinstaller.install()
    except Exception:
        pass

    firefox_options = Options()
    firefox_options.add_argument('--headless')
    firefox_options.add_argument('--disable-gpu')
    firefox_options.add_argument('--no-sandbox')
    firefox_options.set_preference("layout.css.devPixelsPerUnit", "1.0")

    driver = webdriver.Firefox(options=firefox_options)
    pdf_bytes_list = []
    
    try:
        for fig in figures_chunk:
            # Export to PNG in memory if possible, but Bokeh's export_png likes filenames
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_png:
                png_path = tmp_png.name
            
            try:
                export_png(fig, filename=png_path, webdriver=driver)
                # Small sleep to ensure file is written and stable
                time.sleep(0.1)

                # Convert PNG -> PDF bytes
                with Image.open(png_path) as image:
                    if image.mode == 'RGBA':
                        image = image.convert('RGB')
                    
                    pdf_buffer = io.BytesIO()
                    # Resolution 100 is enough for screen-sourced data
                    image.save(pdf_buffer, format='PDF', resolution=100.0)
                    pdf_bytes_list.append(pdf_buffer.getvalue())
            finally:
                if os.path.exists(png_path):
                    os.remove(png_path)
                    
        return pdf_bytes_list
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def create_multi_pdf_from_bokeh_figures(bokeh_figures: list):
    """Create a multi-page PDF from a list of Bokeh figures using parallel workers.

    Processing is parallelized using ThreadPoolExecutor to speed up the slow 
    Selenium-based export process.
    
    Returns:
        Path to the temporary merged PDF file (caller must clean up)
    """
    if not bokeh_figures:
        return None

    # Determine optimal number of workers (max 4 to avoid overwhelming the system)
    num_figures = len(bokeh_figures)
    num_workers = min(num_figures, 4)
    
    # Split figures into chunks for workers
    chunk_size = (num_figures + num_workers - 1) // num_workers
    chunks = [bokeh_figures[i:i + chunk_size] for i in range(0, num_figures, chunk_size)]
    
    # Update actual num_workers based on chunks created
    num_workers = len(chunks)
    
    all_pdf_bytes = []
    
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # Submit all chunks to the executor
        futures = [executor.submit(_export_worker, chunk, i) for i, chunk in enumerate(chunks)]
        
        # Collect results in order
        for future in futures:
            result = future.result()
            all_pdf_bytes.extend(result)

    # Merge all PDF pages into one
    merger = PdfWriter()
    temp_pdfs = []
    
    try:
        for i, pdf_data in enumerate(all_pdf_bytes):
            pdf_stream = io.BytesIO(pdf_data)
            merger.append(pdf_stream)

        # Output the final merged PDF
        temp_output_fd, temp_output_path = tempfile.mkstemp(suffix='.pdf')
        os.close(temp_output_fd)
        
        with open(temp_output_path, 'wb') as output:
            merger.write(output)
            
        return temp_output_path
    finally:
        merger.close()

