#!/usr/bin/python3
from pypdf import PdfWriter
from os import remove, path
import os
import tempfile

def create_multi_pdf_from_charts(chart_objects: list):
    """
    Create a multi-page PDF from a list of chart objects and return temp file path.
    
    Args:
        chart_objects: List of chart objects (e.g., Altair charts)
        
    Returns:
        Path to the temporary merged PDF file (caller must clean up)
    """
    temp_files = []
    merger = PdfWriter()
    temp_output_fd = None
    temp_output_path = None
    
    try:
        # Create temporary PDF for each chart
        for i, chart in enumerate(chart_objects):
            # Create temporary file
            temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
            os.close(temp_fd)  # Close file descriptor, we'll use the path
            
            # Save chart to temporary PDF
            chart.save(temp_path)
            temp_files.append(temp_path)
            
            # Add to merger (pypdf 6.x uses append_pages_from_reader)
            merger.append(temp_path)
        
        # Create temporary output file
        temp_output_fd, temp_output_path = tempfile.mkstemp(suffix='.pdf')
        os.close(temp_output_fd)
        
        # Write merged PDF to temporary file
        with open(temp_output_path, 'wb') as output:
            merger.write(output)
        
        # Return the temp path (caller will handle cleanup)
        return temp_output_path
            
    finally:
        # Clean up individual chart temporary files (but not the merged output)
        for temp_file in temp_files:
            if path.exists(temp_file):
                remove(temp_file)


def create_multi_pdf_from_bokeh_figures(bokeh_figures: list):
    """Create a multi-page PDF from a list of Bokeh figures.

    Each Bokeh figure is exported to PNG via Selenium (export_png) and then converted
    to a single-page PDF. All pages are merged into one PDF.

    Returns:
        Path to the temporary merged PDF file (caller must clean up)
    """
    import io
    import time
    from PIL import Image
    from bokeh.io import export_png
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options

    temp_files = []
    merger = PdfWriter()
    temp_output_fd = None
    temp_output_path = None

    # Try to ensure geckodriver exists
    try:
        import geckodriver_autoinstaller

        geckodriver_autoinstaller.install()
    except Exception:
        pass

    firefox_options = Options()
    firefox_options.add_argument('--headless')
    firefox_options.add_argument('--disable-gpu')
    firefox_options.add_argument('--no-sandbox')

    driver = webdriver.Firefox(options=firefox_options)
    try:
        for fig in bokeh_figures:
            # Export to PNG
            png_fd, png_path = tempfile.mkstemp(suffix='.png')
            os.close(png_fd)
            export_png(fig, filename=png_path, webdriver=driver)
            time.sleep(0.2)

            # Convert PNG -> single-page PDF
            pdf_fd, pdf_path = tempfile.mkstemp(suffix='.pdf')
            os.close(pdf_fd)
            image = Image.open(png_path)
            if image.mode == 'RGBA':
                image = image.convert('RGB')
            pdf_buffer = io.BytesIO()
            image.save(pdf_buffer, format='PDF', resolution=100.0)
            with open(pdf_path, 'wb') as f:
                f.write(pdf_buffer.getvalue())

            # Cleanup PNG
            if path.exists(png_path):
                remove(png_path)

            temp_files.append(pdf_path)
            merger.append(pdf_path)

        temp_output_fd, temp_output_path = tempfile.mkstemp(suffix='.pdf')
        os.close(temp_output_fd)
        with open(temp_output_path, 'wb') as output:
            merger.write(output)
        return temp_output_path
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        for temp_file in temp_files:
            if path.exists(temp_file):
                remove(temp_file)

