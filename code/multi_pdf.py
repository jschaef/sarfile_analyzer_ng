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

